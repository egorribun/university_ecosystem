//! Small, dependency-free Windows process host for the Stryker runner.
//!
//! The Windows implementation creates the target suspended, assigns it to a
//! private Job Object with KILL_ON_JOB_CLOSE, and only resumes it after the
//! assignment succeeds.  The host owns the job handle for the complete target
//! lifetime.  Node controls cancellation through stdin and observes an
//! atomic, token-bound status file; no numeric PID is ever used for cleanup.

#![deny(unsafe_op_in_unsafe_fn)]

use std::io;
use std::time::{Duration, Instant};

/// Run the two-phase owned-job cleanup contract.
///
/// The empty-job proof is intentionally not attempted when the termination
/// request itself fails.  A failed kill request is a terminal, fail-closed
/// result; continuing to poll a known-live job can leave the host blocked for
/// the long normal-completion watchdog.  The real Windows implementation
/// supplies the Job Object call and bounded active-process proof below, while
/// this small seam gives the same policy deterministic fault-injection tests on
/// every build host.
fn terminate_then_wait<Terminate, Wait>(
    terminate: Terminate,
    wait_for_empty: Wait,
) -> io::Result<()>
where
    Terminate: FnOnce() -> io::Result<()>,
    Wait: FnOnce() -> io::Result<()>,
{
    terminate()?;
    wait_for_empty()
}

/// Poll an owned-job emptiness probe with an explicit deadline.
///
/// This helper is deliberately independent from Win32 so the cancellation
/// deadline can be exercised on every CI host.  The native implementation
/// supplies the authoritative Job Object active-process probe; a non-empty
/// result at the deadline is always an error and therefore can never be
/// serialized as a positive quiescence proof.
fn wait_until_empty_bounded<Observe>(
    mut observe_empty: Observe,
    started: Instant,
    timeout: Duration,
    poll_interval: Duration,
) -> io::Result<()>
where
    Observe: FnMut() -> io::Result<bool>,
{
    loop {
        if observe_empty()? {
            return Ok(());
        }
        if started.elapsed() >= timeout {
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "job active-process count did not reach zero",
            ));
        }
        std::thread::sleep(poll_interval);
    }
}

/// Terminate an owned job and require an emptiness proof within `timeout`.
///
/// The termination request is intentionally performed before starting the
/// proof clock.  A successful `TerminateJobObject` call therefore cannot
/// fall through to the four-hour normal-completion watchdog when a descendant
/// is stuck or the proof source is otherwise unavailable.
fn terminate_then_wait_bounded<Terminate, Observe>(
    terminate: Terminate,
    observe_empty: Observe,
    timeout: Duration,
    poll_interval: Duration,
) -> io::Result<()>
where
    Terminate: FnOnce() -> io::Result<()>,
    Observe: FnMut() -> io::Result<bool>,
{
    terminate_then_wait(terminate, || {
        wait_until_empty_bounded(observe_empty, Instant::now(), timeout, poll_interval)
    })
}

#[cfg(test)]
mod lifecycle_policy_tests {
    use super::{terminate_then_wait, terminate_then_wait_bounded};
    use std::cell::Cell;
    use std::io;
    use std::time::{Duration, Instant};

    #[test]
    fn failed_termination_is_returned_without_waiting_for_empty_proof() {
        let waited = Cell::new(false);
        let result = terminate_then_wait(
            || {
                Err(io::Error::new(
                    io::ErrorKind::PermissionDenied,
                    "access denied",
                ))
            },
            || {
                waited.set(true);
                Ok(())
            },
        );

        let error = result.expect_err("a failed termination request must fail closed");
        assert_eq!(error.kind(), io::ErrorKind::PermissionDenied);
        assert!(
            !waited.get(),
            "known-live jobs must not enter an unbounded wait"
        );
    }

    #[test]
    fn successful_termination_still_requires_the_empty_job_proof() {
        let result = terminate_then_wait(
            || Ok(()),
            || {
                Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "active process remains",
                ))
            },
        );

        let error = result.expect_err("a missing empty-job proof must be surfaced");
        assert_eq!(error.kind(), io::ErrorKind::TimedOut);
    }

    #[test]
    fn successful_termination_with_stuck_empty_proof_is_bounded_and_not_quiesced() {
        let termination_attempts = Cell::new(0);
        let started = Instant::now();
        let result = terminate_then_wait_bounded(
            || {
                termination_attempts.set(termination_attempts.get() + 1);
                Ok(())
            },
            || Ok(false),
            Duration::from_millis(20),
            Duration::from_millis(1),
        );

        let error = result.expect_err(
            "a stuck post-termination empty proof must fail closed instead of claiming quiescence",
        );
        assert_eq!(error.kind(), io::ErrorKind::TimedOut);
        assert_eq!(termination_attempts.get(), 1);
        assert!(
            started.elapsed() < Duration::from_secs(1),
            "bounded cancellation proof exceeded its local safety budget"
        );
    }
}

#[cfg(not(windows))]
fn main() {
    eprintln!("stryker-process-host is supported only on Windows");
    std::process::exit(78);
}

#[cfg(windows)]
mod windows_host {
    use super::terminate_then_wait_bounded;
    use std::ffi::OsStr;
    use std::fs::{self, OpenOptions};
    use std::io::{self, BufRead, BufReader, Write};
    use std::mem::{size_of, zeroed};
    use std::os::windows::ffi::OsStrExt;
    use std::path::{Path, PathBuf};
    use std::sync::mpsc::{self, Receiver, TryRecvError};
    use std::thread;
    use std::time::{Duration, Instant};

    type Handle = isize;
    type Dword = u32;
    type Bool = i32;

    const INVALID_HANDLE_VALUE: Handle = -1;
    const WAIT_OBJECT_0: Dword = 0;
    const WAIT_TIMEOUT: Dword = 258;
    const WAIT_FAILED: Dword = 0xffff_ffff;
    const INFINITE: Dword = 0xffff_ffff;
    const ERROR_ACCESS_DENIED: Dword = 5;
    const ERROR_INSUFFICIENT_BUFFER: Dword = 122;
    const ERROR_SHARING_VIOLATION: Dword = 32;
    const ERROR_LOCK_VIOLATION: Dword = 33;
    const GENERIC_READ: Dword = 0x8000_0000;
    const FILE_SHARE_READ: Dword = 0x0000_0001;
    const FILE_SHARE_WRITE: Dword = 0x0000_0002;
    const OPEN_EXISTING: Dword = 3;
    const FILE_ATTRIBUTE_NORMAL: Dword = 0x80;
    const MOVEFILE_REPLACE_EXISTING: Dword = 0x0000_0001;
    const MOVEFILE_WRITE_THROUGH: Dword = 0x0000_0008;
    const STD_OUTPUT_HANDLE: Dword = 0xffff_fff5;
    const STD_ERROR_HANDLE: Dword = 0xffff_fff4;
    const HANDLE_FLAG_INHERIT: Dword = 0x0000_0001;
    const STARTF_USESTDHANDLES: Dword = 0x0000_0100;
    const CREATE_SUSPENDED: Dword = 0x0000_0004;
    const CREATE_UNICODE_ENVIRONMENT: Dword = 0x0000_0400;
    const EXTENDED_STARTUPINFO_PRESENT: Dword = 0x0008_0000;
    const PROC_THREAD_ATTRIBUTE_HANDLE_LIST: usize = 0x0002_0002;
    const JOB_OBJECT_EXTENDED_LIMIT_INFORMATION: Dword = 9;
    const JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION: Dword = 1;
    const JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: Dword = 0x0000_2000;
    const MAX_STATUS_WAIT: Duration = Duration::from_secs(4 * 60 * 60);
    // Cleanup after a startup/proof failure is deliberately much shorter than
    // the normal completion watchdog.  KILL_ON_JOB_CLOSE on JobGuard is the
    // final containment attempt when either operation cannot prove quiescence.
    const FAILURE_CLEANUP_WAIT: Duration = Duration::from_secs(5);
    const STATUS_REPLACEMENT_RETRY_WINDOW: Duration = Duration::from_secs(10);
    const POLL_INTERVAL: Duration = Duration::from_millis(25);
    const PROTOCOL_VERSION: u32 = 1;

    #[repr(C)]
    struct SecurityAttributes {
        length: Dword,
        security_descriptor: *mut core::ffi::c_void,
        inherit_handle: Bool,
    }

    #[repr(C)]
    struct StartupInfo {
        cb: Dword,
        reserved: *mut u16,
        desktop: *mut u16,
        title: *mut u16,
        x: Dword,
        y: Dword,
        x_size: Dword,
        y_size: Dword,
        x_count_chars: Dword,
        y_count_chars: Dword,
        fill_attribute: Dword,
        flags: Dword,
        show_window: u16,
        reserved2: u16,
        reserved2_ptr: *mut u8,
        stdin: Handle,
        stdout: Handle,
        stderr: Handle,
    }

    #[repr(C)]
    struct StartupInfoEx {
        startup_info: StartupInfo,
        attribute_list: *mut core::ffi::c_void,
    }

    #[repr(C)]
    struct ProcessInformation {
        process: Handle,
        thread: Handle,
        process_id: Dword,
        thread_id: Dword,
    }

    #[repr(C)]
    struct BasicLimitInformation {
        per_process_user_time_limit: i64,
        per_job_user_time_limit: i64,
        limit_flags: Dword,
        minimum_working_set_size: usize,
        maximum_working_set_size: usize,
        active_process_limit: Dword,
        affinity: usize,
        priority_class: Dword,
        scheduling_class: Dword,
    }

    #[repr(C)]
    struct IoCounters {
        read_operation_count: u64,
        write_operation_count: u64,
        other_operation_count: u64,
        read_transfer_count: u64,
        write_transfer_count: u64,
        other_transfer_count: u64,
    }

    #[repr(C)]
    struct ExtendedLimitInformation {
        basic_limit_information: BasicLimitInformation,
        io_info: IoCounters,
        process_memory_limit: usize,
        job_memory_limit: usize,
        peak_process_memory_used: usize,
        peak_job_memory_used: usize,
    }

    #[repr(C)]
    struct BasicAccountingInformation {
        total_user_time: i64,
        total_kernel_time: i64,
        this_period_total_user_time: i64,
        this_period_total_kernel_time: i64,
        total_page_fault_count: Dword,
        total_processes: Dword,
        active_processes: Dword,
        total_terminated_processes: Dword,
    }

    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn GetLastError() -> Dword;
        fn GetStdHandle(which: Dword) -> Handle;
        fn CreateFileW(
            name: *const u16,
            access: Dword,
            share_mode: Dword,
            security: *const SecurityAttributes,
            creation: Dword,
            flags: Dword,
            template: Handle,
        ) -> Handle;
        fn GetHandleInformation(handle: Handle, flags: *mut Dword) -> Bool;
        fn SetHandleInformation(handle: Handle, mask: Dword, flags: Dword) -> Bool;
        fn CloseHandle(handle: Handle) -> Bool;
        fn MoveFileExW(existing_name: *const u16, new_name: *const u16, flags: Dword) -> Bool;
        fn CreateJobObjectW(security: *const SecurityAttributes, name: *const u16) -> Handle;
        fn SetInformationJobObject(
            job: Handle,
            class: Dword,
            info: *const core::ffi::c_void,
            length: Dword,
        ) -> Bool;
        fn AssignProcessToJobObject(job: Handle, process: Handle) -> Bool;
        fn TerminateJobObject(job: Handle, code: Dword) -> Bool;
        fn CreateProcessW(
            application: *const u16,
            command_line: *mut u16,
            process_security: *const SecurityAttributes,
            thread_security: *const SecurityAttributes,
            inherit_handles: Bool,
            creation_flags: Dword,
            environment: *mut core::ffi::c_void,
            current_directory: *const u16,
            startup: *const StartupInfoEx,
            process_info: *mut ProcessInformation,
        ) -> Bool;
        fn ResumeThread(thread: Handle) -> Dword;
        fn TerminateProcess(process: Handle, code: Dword) -> Bool;
        fn WaitForSingleObject(handle: Handle, milliseconds: Dword) -> Dword;
        fn GetExitCodeProcess(process: Handle, code: *mut Dword) -> Bool;
        fn QueryInformationJobObject(
            job: Handle,
            class: Dword,
            info: *mut core::ffi::c_void,
            length: Dword,
            returned_length: *mut Dword,
        ) -> Bool;
        fn InitializeProcThreadAttributeList(
            list: *mut core::ffi::c_void,
            count: Dword,
            flags: Dword,
            size: *mut usize,
        ) -> Bool;
        fn UpdateProcThreadAttribute(
            list: *mut core::ffi::c_void,
            flags: Dword,
            attribute: usize,
            value: *const core::ffi::c_void,
            size: usize,
            previous: *mut core::ffi::c_void,
            return_size: *mut usize,
        ) -> Bool;
        fn DeleteProcThreadAttributeList(list: *mut core::ffi::c_void);
    }

    #[derive(Debug)]
    struct Config {
        target: PathBuf,
        cwd: PathBuf,
        status: PathBuf,
        token: String,
        args: Vec<String>,
    }

    #[derive(Debug)]
    struct OwnedProcess {
        process: Handle,
        thread: Handle,
        process_id: Dword,
    }

    impl Drop for OwnedProcess {
        fn drop(&mut self) {
            // The handles are each owned by this guard exactly once.
            if self.thread != 0 && self.thread != INVALID_HANDLE_VALUE {
                unsafe {
                    CloseHandle(self.thread);
                }
                self.thread = 0;
            }
            if self.process != 0 && self.process != INVALID_HANDLE_VALUE {
                unsafe {
                    CloseHandle(self.process);
                }
                self.process = 0;
            }
        }
    }

    struct JobGuard(Handle);

    impl Drop for JobGuard {
        fn drop(&mut self) {
            if self.0 != 0 && self.0 != INVALID_HANDLE_VALUE {
                unsafe {
                    // KILL_ON_JOB_CLOSE is the final crash/EOF safety net.
                    CloseHandle(self.0);
                }
                self.0 = 0;
            }
        }
    }

    struct AttributeListGuard {
        ptr: *mut core::ffi::c_void,
        _storage: Vec<usize>,
    }

    impl Drop for AttributeListGuard {
        fn drop(&mut self) {
            if !self.ptr.is_null() {
                unsafe {
                    DeleteProcThreadAttributeList(self.ptr);
                }
                self.ptr = core::ptr::null_mut();
            }
        }
    }

    struct InheritableHandle {
        handle: Handle,
        original_flags: Dword,
        owned: bool,
    }

    impl InheritableHandle {
        fn restore(&self) -> io::Result<()> {
            let ok = unsafe {
                SetHandleInformation(self.handle, HANDLE_FLAG_INHERIT, self.original_flags)
            };
            if ok == 0 {
                return Err(last_error("SetHandleInformation restore"));
            }
            Ok(())
        }
    }

    impl Drop for InheritableHandle {
        fn drop(&mut self) {
            if self.owned && self.handle != 0 && self.handle != INVALID_HANDLE_VALUE {
                unsafe {
                    CloseHandle(self.handle);
                }
                self.handle = 0;
            }
        }
    }

    fn win32_error(operation: &str, code: Dword) -> io::Error {
        io::Error::other(format!("{operation} failed with Win32 error {code}"))
    }

    fn last_error(operation: &str) -> io::Error {
        win32_error(operation, unsafe { GetLastError() })
    }

    fn to_wide(value: &str) -> Vec<u16> {
        OsStr::new(value)
            .encode_wide()
            .chain(std::iter::once(0))
            .collect()
    }

    fn path_to_wide(path: &Path) -> Vec<u16> {
        path.as_os_str()
            .encode_wide()
            .chain(std::iter::once(0))
            .collect()
    }

    fn valid_handle(handle: Handle) -> bool {
        handle != 0 && handle != INVALID_HANDLE_VALUE
    }

    fn assert_safe_token(token: &str) -> io::Result<()> {
        if token.is_empty()
            || token.len() > 128
            || !token
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-' || byte == b'_')
        {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "job token has an unsafe shape",
            ));
        }
        Ok(())
    }

    fn parse_config() -> io::Result<Config> {
        let mut target = None;
        let mut cwd = None;
        let mut status = None;
        let mut token = None;
        let mut args = Vec::new();
        let mut iter = std::env::args_os().skip(1);
        while let Some(key) = iter.next() {
            let key = key.to_string_lossy().into_owned();
            let value = iter.next().ok_or_else(|| {
                io::Error::new(
                    io::ErrorKind::InvalidInput,
                    format!("missing value for {key}"),
                )
            })?;
            let value = value.to_string_lossy().into_owned();
            match key.as_str() {
                "--target" => target = Some(value),
                "--cwd" => cwd = Some(value),
                "--status" => status = Some(value),
                "--token" => token = Some(value),
                "--arg" => args.push(value),
                _ => {
                    return Err(io::Error::new(
                        io::ErrorKind::InvalidInput,
                        format!("unknown host option {key}"),
                    ))
                }
            }
        }
        let target =
            PathBuf::from(target.ok_or_else(|| {
                io::Error::new(io::ErrorKind::InvalidInput, "--target is required")
            })?);
        let cwd = PathBuf::from(
            cwd.ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "--cwd is required"))?,
        );
        let status =
            PathBuf::from(status.ok_or_else(|| {
                io::Error::new(io::ErrorKind::InvalidInput, "--status is required")
            })?);
        let token = token
            .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "--token is required"))?;
        if !target.is_absolute() || !cwd.is_absolute() || !status.is_absolute() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "target, cwd, and status paths must be absolute",
            ));
        }
        if !target.is_file() {
            return Err(io::Error::new(
                io::ErrorKind::NotFound,
                "target executable does not exist",
            ));
        }
        if !cwd.is_dir() {
            return Err(io::Error::new(
                io::ErrorKind::NotFound,
                "target working directory does not exist",
            ));
        }
        if status.exists() || !status.parent().is_some_and(Path::is_dir) {
            return Err(io::Error::new(
                io::ErrorKind::AlreadyExists,
                "status path is not fresh or its parent is missing",
            ));
        }
        assert_safe_token(&token)?;
        Ok(Config {
            target,
            cwd,
            status,
            token,
            args,
        })
    }

    fn escape_json(value: &str) -> String {
        value
            .chars()
            .flat_map(|character| match character {
                '"' => "\\\"".chars().collect::<Vec<_>>(),
                '\\' => "\\\\".chars().collect::<Vec<_>>(),
                '\n' => "\\n".chars().collect::<Vec<_>>(),
                '\r' => "\\r".chars().collect::<Vec<_>>(),
                '\t' => "\\t".chars().collect::<Vec<_>>(),
                character if character.is_control() => {
                    format!("\\u{:04x}", character as u32).chars().collect()
                }
                character => vec![character],
            })
            .collect()
    }

    struct StatusSnapshot<'a> {
        state: &'a str,
        token: &'a str,
        host_pid: Dword,
        target_pid: Option<Dword>,
        exit_code: Option<Dword>,
        quiesced: bool,
        ready_acknowledged: bool,
        reason: Option<&'a str>,
    }

    fn status_json(snapshot: &StatusSnapshot<'_>) -> String {
        let target = snapshot
            .target_pid
            .map_or_else(|| "null".to_string(), |pid| pid.to_string());
        let exit = snapshot
            .exit_code
            .map_or_else(|| "null".to_string(), |code| code.to_string());
        let reason = snapshot.reason.map_or_else(
            || "null".to_string(),
            |value| format!("\"{}\"", escape_json(value)),
        );
        format!(
            "{{\"schemaVersion\":1,\"protocolVersion\":{PROTOCOL_VERSION},\"state\":\"{}\",\"hostPid\":{},\"targetPid\":{},\"jobToken\":\"{}\",\"exitCode\":{},\"quiesced\":{},\"readyAcknowledged\":{},\"reason\":{}}}\n",
            escape_json(snapshot.state),
            snapshot.host_pid,
            target,
            escape_json(snapshot.token),
            exit,
            snapshot.quiesced,
            snapshot.ready_acknowledged,
            reason
        )
    }

    fn write_status(path: &Path, content: &str) -> io::Result<()> {
        let temp = path.with_file_name(format!(
            ".{}.{}.tmp",
            path.file_name().unwrap_or_default().to_string_lossy(),
            std::process::id()
        ));
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temp)?;
        file.write_all(content.as_bytes())?;
        file.sync_all()?;
        drop(file);
        // `std::fs::rename` cannot replace an existing destination on Windows.
        // MoveFileEx(REPLACE_EXISTING|WRITE_THROUGH) gives each status update
        // one atomic, durable replacement while retaining the old proof until
        // the new file is ready.
        let temp_wide = path_to_wide(&temp);
        let path_wide = path_to_wide(path);
        let started = Instant::now();
        loop {
            if unsafe {
                MoveFileExW(
                    temp_wide.as_ptr(),
                    path_wide.as_ptr(),
                    MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
                )
            } != 0
            {
                return Ok(());
            }
            let code = unsafe { GetLastError() };
            let retryable = matches!(
                code,
                ERROR_ACCESS_DENIED | ERROR_SHARING_VIOLATION | ERROR_LOCK_VIOLATION
            );
            if !retryable || started.elapsed() >= STATUS_REPLACEMENT_RETRY_WINDOW {
                let error = win32_error("MoveFileExW status replacement", code);
                let _ = fs::remove_file(&temp);
                return Err(error);
            }
            thread::sleep(POLL_INTERVAL);
        }
    }

    fn quote_windows_arg(value: &str) -> String {
        if !value.is_empty()
            && !value
                .bytes()
                .any(|byte| matches!(byte, b' ' | b'\t' | b'"'))
        {
            return value.to_string();
        }
        let mut result = String::from("\"");
        let mut slashes = 0usize;
        for character in value.chars() {
            if character == '\\' {
                slashes += 1;
                continue;
            }
            if character == '"' {
                result.extend(std::iter::repeat_n('\\', slashes * 2 + 1));
                result.push('"');
            } else {
                result.extend(std::iter::repeat_n('\\', slashes));
                result.push(character);
            }
            slashes = 0;
        }
        result.extend(std::iter::repeat_n('\\', slashes * 2));
        result.push('"');
        result
    }

    fn command_line(target: &Path, args: &[String]) -> Vec<u16> {
        let mut command = quote_windows_arg(&target.to_string_lossy());
        for argument in args {
            command.push(' ');
            command.push_str(&quote_windows_arg(argument));
        }
        to_wide(&command)
    }

    fn make_nul_handle() -> io::Result<InheritableHandle> {
        let nul = to_wide("NUL");
        let handle = unsafe {
            CreateFileW(
                nul.as_ptr(),
                GENERIC_READ,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                core::ptr::null(),
                OPEN_EXISTING,
                FILE_ATTRIBUTE_NORMAL,
                0,
            )
        };
        if !valid_handle(handle) {
            return Err(last_error("CreateFileW(NUL)"));
        }
        if unsafe { SetHandleInformation(handle, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT) } == 0 {
            unsafe {
                CloseHandle(handle);
            }
            return Err(last_error("SetHandleInformation NUL inherit"));
        }
        Ok(InheritableHandle {
            handle,
            original_flags: 0,
            owned: true,
        })
    }

    fn make_inheritable(handle: Handle, owned: bool) -> io::Result<InheritableHandle> {
        if !valid_handle(handle) {
            return make_nul_handle();
        }
        let mut flags = 0;
        if unsafe { GetHandleInformation(handle, &mut flags) } == 0 {
            return Err(last_error("GetHandleInformation"));
        }
        if unsafe { SetHandleInformation(handle, HANDLE_FLAG_INHERIT, flags | HANDLE_FLAG_INHERIT) }
            == 0
        {
            return Err(last_error("SetHandleInformation inherit"));
        }
        Ok(InheritableHandle {
            handle,
            original_flags: flags,
            owned,
        })
    }

    fn build_attribute_list(handles: &[Handle]) -> io::Result<AttributeListGuard> {
        let mut bytes = 0usize;
        unsafe {
            InitializeProcThreadAttributeList(core::ptr::null_mut(), 1, 0, &mut bytes);
        }
        if bytes == 0 {
            let error = unsafe { GetLastError() };
            if error != ERROR_INSUFFICIENT_BUFFER {
                return Err(last_error("InitializeProcThreadAttributeList size"));
            }
        }
        let words = bytes.div_ceil(size_of::<usize>());
        let mut storage = vec![0usize; words.max(1)];
        let ptr = storage.as_mut_ptr().cast::<core::ffi::c_void>();
        if unsafe { InitializeProcThreadAttributeList(ptr, 1, 0, &mut bytes) } == 0 {
            return Err(last_error("InitializeProcThreadAttributeList"));
        }
        let ok = unsafe {
            UpdateProcThreadAttribute(
                ptr,
                0,
                PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
                handles.as_ptr().cast(),
                std::mem::size_of_val(handles),
                core::ptr::null_mut(),
                // lpReturnSize is reserved and must be NULL.
                core::ptr::null_mut(),
            )
        };
        if ok == 0 {
            return Err(last_error("UpdateProcThreadAttribute handle list"));
        }
        Ok(AttributeListGuard {
            ptr,
            _storage: storage,
        })
    }

    fn create_suspended_process(config: &Config) -> io::Result<OwnedProcess> {
        let stdin = make_nul_handle()?;
        let stdout = make_inheritable(unsafe { GetStdHandle(STD_OUTPUT_HANDLE) }, false)?;
        let stderr = make_inheritable(unsafe { GetStdHandle(STD_ERROR_HANDLE) }, false)?;
        let inherited = [stdin.handle, stdout.handle, stderr.handle];
        let attributes = build_attribute_list(&inherited)?;
        let mut startup: StartupInfoEx = unsafe { zeroed() };
        startup.startup_info.cb = size_of::<StartupInfoEx>() as Dword;
        startup.startup_info.flags = STARTF_USESTDHANDLES;
        startup.startup_info.stdin = stdin.handle;
        startup.startup_info.stdout = stdout.handle;
        startup.startup_info.stderr = stderr.handle;
        startup.attribute_list = attributes.ptr;
        let application = path_to_wide(&config.target);
        let mut command = command_line(&config.target, &config.args);
        let cwd = path_to_wide(&config.cwd);
        let mut info: ProcessInformation = unsafe { zeroed() };
        let flags = CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT | EXTENDED_STARTUPINFO_PRESENT;
        let created = unsafe {
            CreateProcessW(
                application.as_ptr(),
                command.as_mut_ptr(),
                core::ptr::null(),
                core::ptr::null(),
                1,
                flags,
                core::ptr::null_mut(),
                cwd.as_ptr(),
                &startup,
                &mut info,
            )
        };
        let creation_error = (created == 0).then(|| last_error("CreateProcessW"));
        let mut restore_error = None;
        if let Err(error) = stdout.restore() {
            restore_error = Some(error);
        }
        if let Err(error) = stderr.restore() {
            if restore_error.is_none() {
                restore_error = Some(error);
            }
        }
        if let Some(error) = creation_error {
            return Err(error);
        }
        if let Some(error) = restore_error {
            let cleanup = terminate_process_and_wait(info.process, 70, FAILURE_CLEANUP_WAIT);
            // The process/thread handles are not wrapped in `OwnedProcess` on
            // this error path, so close both explicitly after the suspended
            // child has been terminated.  A failed termination is retained in
            // the returned error and never silently converted into success.
            unsafe {
                CloseHandle(info.thread);
                CloseHandle(info.process);
            }
            return Err(match cleanup {
                Ok(()) => error,
                Err(cleanup_error) => io::Error::other(format!(
                    "{error}; suspended target cleanup failed: {cleanup_error}"
                )),
            });
        }
        // Attribute-list cleanup and the explicit standard-handle closure both
        // happen before the primary thread is resumed.  The target never gets
        // the job or control handles.
        drop(attributes);
        drop(stdout);
        drop(stderr);
        drop(stdin);
        Ok(OwnedProcess {
            process: info.process,
            thread: info.thread,
            process_id: info.process_id,
        })
    }

    fn configure_job(job: Handle) -> io::Result<()> {
        let mut limits: ExtendedLimitInformation = unsafe { zeroed() };
        limits.basic_limit_information.limit_flags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        let ok = unsafe {
            SetInformationJobObject(
                job,
                JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                (&limits as *const ExtendedLimitInformation).cast(),
                size_of::<ExtendedLimitInformation>() as Dword,
            )
        };
        if ok == 0 {
            return Err(last_error("SetInformationJobObject"));
        }
        Ok(())
    }

    fn active_processes(job: Handle) -> io::Result<Dword> {
        let mut accounting: BasicAccountingInformation = unsafe { zeroed() };
        let mut returned = 0;
        let ok = unsafe {
            QueryInformationJobObject(
                job,
                JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
                (&mut accounting as *mut BasicAccountingInformation).cast(),
                size_of::<BasicAccountingInformation>() as Dword,
                &mut returned,
            )
        };
        if ok == 0 {
            return Err(last_error("QueryInformationJobObject"));
        }
        Ok(accounting.active_processes)
    }

    fn wait_for_process(process: Handle) -> io::Result<Dword> {
        let result = unsafe { WaitForSingleObject(process, INFINITE) };
        if result != WAIT_OBJECT_0 {
            return Err(last_error("WaitForSingleObject"));
        }
        let mut code = 0;
        if unsafe { GetExitCodeProcess(process, &mut code) } == 0 {
            return Err(last_error("GetExitCodeProcess"));
        }
        Ok(code)
    }

    fn terminate_job(job: Handle, code: Dword) -> io::Result<()> {
        if unsafe { TerminateJobObject(job, code) } == 0 {
            return Err(last_error("TerminateJobObject"));
        }
        Ok(())
    }

    fn terminate_and_prove_empty(job: Handle, code: Dword, timeout: Duration) -> io::Result<()> {
        terminate_then_wait_bounded(
            || terminate_job(job, code),
            || active_processes(job).map(|active| active == 0),
            timeout,
            POLL_INTERVAL,
        )
    }

    fn terminate_process_and_wait(
        process: Handle,
        code: Dword,
        timeout: Duration,
    ) -> io::Result<()> {
        if unsafe { TerminateProcess(process, code) } == 0 {
            return Err(last_error("TerminateProcess"));
        }
        let timeout_ms = timeout.as_millis().min(Dword::MAX as u128) as Dword;
        let wait_result = unsafe { WaitForSingleObject(process, timeout_ms) };
        if wait_result != WAIT_OBJECT_0 {
            return Err(if wait_result == WAIT_TIMEOUT {
                io::Error::new(io::ErrorKind::TimedOut, "terminated process did not exit")
            } else {
                last_error("WaitForSingleObject terminated process")
            });
        }
        Ok(())
    }

    fn clone_io_error(error: &io::Error) -> io::Error {
        io::Error::new(error.kind(), error.to_string())
    }

    fn start_control_reader() -> Receiver<ControlMessage> {
        let (sender, receiver) = mpsc::channel();
        thread::spawn(move || {
            let stdin = io::stdin();
            let mut reader = BufReader::new(stdin.lock());
            let mut line = String::new();
            match reader.read_line(&mut line) {
                Ok(0) => {
                    let _ = sender.send(ControlMessage::Eof);
                }
                Ok(_) if line.trim_end_matches(['\r', '\n']) == "TERMINATE" => {
                    let _ = sender.send(ControlMessage::Terminate);
                }
                Ok(_) => {
                    let _ = sender.send(ControlMessage::Invalid);
                }
                Err(_) => {
                    let _ = sender.send(ControlMessage::Eof);
                }
            }
        });
        receiver
    }

    enum ControlMessage {
        Terminate,
        Eof,
        Invalid,
    }

    fn poll_control_with_terminator<Terminate>(
        controls: &Receiver<ControlMessage>,
        job: Handle,
        termination_requested: &mut bool,
        control_error: &mut Option<io::Error>,
        termination_error: &mut Option<io::Error>,
        terminate: Terminate,
    ) where
        Terminate: Fn(Handle, Dword) -> io::Result<()>,
    {
        let request_termination =
            |code: Dword,
             termination_requested: &mut bool,
             control_error: &mut Option<io::Error>,
             termination_error: &mut Option<io::Error>| {
                if *termination_requested {
                    return;
                }
                *termination_requested = true;
                if let Err(error) = terminate(job, code) {
                    if control_error.is_none() {
                        *control_error = Some(clone_io_error(&error));
                    }
                    if termination_error.is_none() {
                        *termination_error = Some(error);
                    }
                }
            };
        match controls.try_recv() {
            Ok(ControlMessage::Terminate | ControlMessage::Eof) if !*termination_requested => {
                request_termination(143, termination_requested, control_error, termination_error);
            }
            Ok(ControlMessage::Invalid) => {
                if control_error.is_none() {
                    *control_error = Some(io::Error::new(
                        io::ErrorKind::InvalidInput,
                        "invalid control command",
                    ));
                }
                request_termination(70, termination_requested, control_error, termination_error);
            }
            Ok(_) => {}
            Err(TryRecvError::Empty) => {}
            Err(TryRecvError::Disconnected) => {
                request_termination(143, termination_requested, control_error, termination_error);
            }
        }
    }

    fn poll_control(
        controls: &Receiver<ControlMessage>,
        job: Handle,
        termination_requested: &mut bool,
        control_error: &mut Option<io::Error>,
        termination_error: &mut Option<io::Error>,
    ) {
        poll_control_with_terminator(
            controls,
            job,
            termination_requested,
            control_error,
            termination_error,
            terminate_job,
        );
    }

    fn wait_for_empty_with_control(
        job: Handle,
        controls: &Receiver<ControlMessage>,
        termination_requested: &mut bool,
        control_error: &mut Option<io::Error>,
        termination_error: &mut Option<io::Error>,
        started: Instant,
    ) -> io::Result<()> {
        // A cancellation proof has a short, independent deadline.  Keep the
        // four-hour watchdog exclusively for normal target completion, where
        // a long-running descendant may still be making legitimate progress.
        // If cancellation arrives while this loop is already running, start
        // the bounded clock at the exact poll that observed the request.
        let mut cancellation_started = if *termination_requested {
            Some(Instant::now())
        } else {
            None
        };
        loop {
            // Keep consuming the dedicated control pipe even after the host's
            // direct target has exited.  A normal target can leave detached
            // descendants in the Job Object; cancellation must still be able
            // to terminate those members instead of waiting for the watchdog.
            let was_termination_requested = *termination_requested;
            poll_control(
                controls,
                job,
                termination_requested,
                control_error,
                termination_error,
            );
            if *termination_requested && !was_termination_requested {
                cancellation_started = Some(Instant::now());
            }
            if let Some(error) = termination_error.as_ref() {
                // Do not wait for the four-hour normal-completion watchdog
                // after a known failed kill request.  JobGuard's
                // KILL_ON_JOB_CLOSE policy is the final containment attempt.
                return Err(clone_io_error(error));
            }
            let active = active_processes(job)?;
            if active == 0 {
                return Ok(());
            }
            let (proof_started, proof_timeout, timeout_reason) = cancellation_started.map_or(
                (
                    started,
                    MAX_STATUS_WAIT,
                    "job active-process count did not reach zero",
                ),
                |cancellation_started| {
                    (
                        cancellation_started,
                        FAILURE_CLEANUP_WAIT,
                        "job active-process count did not reach zero after cancellation",
                    )
                },
            );
            if proof_started.elapsed() >= proof_timeout {
                return Err(io::Error::new(io::ErrorKind::TimedOut, timeout_reason));
            }
            thread::sleep(POLL_INTERVAL);
        }
    }

    fn run() -> io::Result<i32> {
        let config = parse_config()?;
        let host_pid = std::process::id();
        write_status(
            &config.status,
            &status_json(&StatusSnapshot {
                state: "starting",
                token: &config.token,
                host_pid,
                target_pid: None,
                exit_code: None,
                quiesced: false,
                ready_acknowledged: false,
                reason: None,
            }),
        )?;
        let null_name = core::ptr::null();
        let job = unsafe { CreateJobObjectW(core::ptr::null(), null_name) };
        if !valid_handle(job) {
            let error = last_error("CreateJobObjectW");
            let _ = write_status(
                &config.status,
                &status_json(&StatusSnapshot {
                    state: "error",
                    token: &config.token,
                    host_pid,
                    target_pid: None,
                    exit_code: None,
                    quiesced: false,
                    ready_acknowledged: false,
                    reason: Some(&error.to_string()),
                }),
            );
            return Err(error);
        }
        let job = JobGuard(job);
        if let Err(error) = configure_job(job.0) {
            let _ = write_status(
                &config.status,
                &status_json(&StatusSnapshot {
                    state: "error",
                    token: &config.token,
                    host_pid,
                    target_pid: None,
                    exit_code: None,
                    quiesced: false,
                    ready_acknowledged: false,
                    reason: Some(&error.to_string()),
                }),
            );
            return Err(error);
        }
        let target = match create_suspended_process(&config) {
            Ok(process) => process,
            Err(error) => {
                let _ = write_status(
                    &config.status,
                    &status_json(&StatusSnapshot {
                        state: "error",
                        token: &config.token,
                        host_pid,
                        target_pid: None,
                        exit_code: None,
                        quiesced: false,
                        ready_acknowledged: false,
                        reason: Some(&error.to_string()),
                    }),
                );
                return Err(error);
            }
        };
        let target_pid = target.process_id;
        if unsafe { AssignProcessToJobObject(job.0, target.process) } == 0 {
            let error = last_error("AssignProcessToJobObject");
            let cleanup = terminate_process_and_wait(target.process, 70, FAILURE_CLEANUP_WAIT);
            let _ = write_status(
                &config.status,
                &status_json(&StatusSnapshot {
                    state: "error",
                    token: &config.token,
                    host_pid,
                    target_pid: Some(target_pid),
                    exit_code: None,
                    quiesced: false,
                    ready_acknowledged: false,
                    reason: Some(&cleanup.as_ref().err().map_or_else(
                        || error.to_string(),
                        |cleanup_error| {
                            format!("{error}; suspended target cleanup failed: {cleanup_error}")
                        },
                    )),
                }),
            );
            return Err(error);
        }
        if unsafe { ResumeThread(target.thread) } == u32::MAX {
            let error = last_error("ResumeThread");
            let cleanup = terminate_and_prove_empty(job.0, 70, FAILURE_CLEANUP_WAIT);
            let _ = write_status(
                &config.status,
                &status_json(&StatusSnapshot {
                    state: "error",
                    token: &config.token,
                    host_pid,
                    target_pid: Some(target_pid),
                    exit_code: None,
                    quiesced: false,
                    ready_acknowledged: false,
                    reason: Some(&cleanup.as_ref().err().map_or_else(
                        || error.to_string(),
                        |cleanup_error| format!("{error}; job cleanup failed: {cleanup_error}"),
                    )),
                }),
            );
            return Err(error);
        }
        write_status(
            &config.status,
            &status_json(&StatusSnapshot {
                state: "ready",
                token: &config.token,
                host_pid,
                target_pid: Some(target_pid),
                exit_code: None,
                quiesced: false,
                ready_acknowledged: true,
                reason: None,
            }),
        )?;
        let controls = start_control_reader();
        let mut termination_requested = false;
        let mut control_error = None;
        let mut termination_error = None;
        loop {
            poll_control(
                &controls,
                job.0,
                &mut termination_requested,
                &mut control_error,
                &mut termination_error,
            );
            if let Some(error) = termination_error.as_ref() {
                // The target may still be running when TerminateJobObject
                // fails.  Abort immediately instead of waiting for its handle
                // (or the four-hour completion watchdog); dropping JobGuard
                // invokes the kill-on-close containment policy.
                let error = clone_io_error(error);
                let _ = write_status(
                    &config.status,
                    &status_json(&StatusSnapshot {
                        state: "error",
                        token: &config.token,
                        host_pid,
                        target_pid: Some(target_pid),
                        exit_code: None,
                        quiesced: false,
                        ready_acknowledged: true,
                        reason: Some(&error.to_string()),
                    }),
                );
                return Err(error);
            }
            let target_state = unsafe { WaitForSingleObject(target.process, 0) };
            if target_state == WAIT_FAILED {
                let error = last_error("WaitForSingleObject target");
                let cleanup = terminate_and_prove_empty(job.0, 70, FAILURE_CLEANUP_WAIT);
                let _ = write_status(
                    &config.status,
                    &status_json(&StatusSnapshot {
                        state: "error",
                        token: &config.token,
                        host_pid,
                        target_pid: Some(target_pid),
                        exit_code: None,
                        quiesced: false,
                        ready_acknowledged: true,
                        reason: Some(&cleanup.as_ref().err().map_or_else(
                            || error.to_string(),
                            |cleanup_error| format!("{error}; job cleanup failed: {cleanup_error}"),
                        )),
                    }),
                );
                return Err(error);
            }
            if target_state != WAIT_OBJECT_0 && target_state != WAIT_TIMEOUT {
                let error =
                    io::Error::other(format!("unexpected target wait result {target_state}"));
                let cleanup = terminate_and_prove_empty(job.0, 70, FAILURE_CLEANUP_WAIT);
                let _ = write_status(
                    &config.status,
                    &status_json(&StatusSnapshot {
                        state: "error",
                        token: &config.token,
                        host_pid,
                        target_pid: Some(target_pid),
                        exit_code: None,
                        quiesced: false,
                        ready_acknowledged: true,
                        reason: Some(&cleanup.as_ref().err().map_or_else(
                            || error.to_string(),
                            |cleanup_error| format!("{error}; job cleanup failed: {cleanup_error}"),
                        )),
                    }),
                );
                return Err(error);
            }
            if target_state == WAIT_OBJECT_0 {
                break;
            }
            thread::sleep(POLL_INTERVAL);
        }
        let target_code = match wait_for_process(target.process) {
            Ok(code) => code,
            Err(error) => {
                let cleanup = terminate_and_prove_empty(job.0, 70, FAILURE_CLEANUP_WAIT);
                let reason = cleanup.as_ref().err().map_or_else(
                    || error.to_string(),
                    |cleanup_error| format!("{error}; job cleanup failed: {cleanup_error}"),
                );
                let _ = write_status(
                    &config.status,
                    &status_json(&StatusSnapshot {
                        state: "error",
                        token: &config.token,
                        host_pid,
                        target_pid: Some(target_pid),
                        exit_code: None,
                        quiesced: false,
                        ready_acknowledged: true,
                        reason: Some(&reason),
                    }),
                );
                return Err(error);
            }
        };
        let proof_started = Instant::now();
        let empty_result = wait_for_empty_with_control(
            job.0,
            &controls,
            &mut termination_requested,
            &mut control_error,
            &mut termination_error,
            proof_started,
        );
        if termination_requested {
            let result = termination_error
                .or(control_error)
                .or_else(|| empty_result.err());
            let state = if result.is_some() {
                "error"
            } else {
                "job_terminated"
            };
            let quiesced = result.is_none();
            let reason = result.as_ref().map(ToString::to_string);
            let status_result = write_status(
                &config.status,
                &status_json(&StatusSnapshot {
                    state,
                    token: &config.token,
                    host_pid,
                    target_pid: Some(target_pid),
                    exit_code: Some(target_code),
                    quiesced,
                    ready_acknowledged: true,
                    reason: reason.as_deref(),
                }),
            );
            status_result?;
            return Ok(if quiesced { 143 } else { 70 });
        }
        match empty_result {
            Ok(()) => {
                write_status(
                    &config.status,
                    &status_json(&StatusSnapshot {
                        state: "job_empty",
                        token: &config.token,
                        host_pid,
                        target_pid: Some(target_pid),
                        exit_code: Some(target_code),
                        quiesced: true,
                        ready_acknowledged: true,
                        reason: None,
                    }),
                )?;
                Ok(target_code as i32)
            }
            Err(error) => {
                // A target that exits while leaving members in the job is not
                // a release-valid success.  Contain the members, prove the
                // empty job, and report a non-zero host result.
                let cleanup = terminate_and_prove_empty(job.0, 70, FAILURE_CLEANUP_WAIT);
                let quiesced = cleanup.is_ok();
                let reason = cleanup.as_ref().err().map_or_else(
                    || error.to_string(),
                    |cleanup_error| format!("{error}; job cleanup failed: {cleanup_error}"),
                );
                let status_result = write_status(
                    &config.status,
                    &status_json(&StatusSnapshot {
                        state: if quiesced { "job_terminated" } else { "error" },
                        token: &config.token,
                        host_pid,
                        target_pid: Some(target_pid),
                        exit_code: Some(70),
                        quiesced,
                        ready_acknowledged: true,
                        reason: Some(&reason),
                    }),
                );
                status_result?;
                Ok(70)
            }
        }
    }

    pub fn entry() -> i32 {
        match run() {
            Ok(code) => code,
            Err(error) => {
                eprintln!("stryker-process-host: {error}");
                70
            }
        }
    }

    #[cfg(test)]
    mod lifecycle_tests {
        use super::*;
        use std::cell::Cell;
        use std::sync::mpsc;
        use std::time::Duration;

        #[test]
        fn access_denied_termination_is_bounded_and_emits_false_quiescence() {
            let (sender, receiver) = mpsc::channel();
            sender
                .send(ControlMessage::Terminate)
                .expect("control channel remains open for the test");
            let mut termination_requested = false;
            let mut control_error = None;
            let mut termination_error = None;
            let calls = Cell::new(0);
            poll_control_with_terminator(
                &receiver,
                123,
                &mut termination_requested,
                &mut control_error,
                &mut termination_error,
                |_job, _code| {
                    calls.set(calls.get() + 1);
                    Err(io::Error::new(
                        io::ErrorKind::PermissionDenied,
                        "TerminateJobObject failed with Win32 error 5",
                    ))
                },
            );
            assert!(termination_requested);
            assert_eq!(calls.get(), 1);
            assert!(control_error.is_some());
            assert!(termination_error.is_some());

            let started = Instant::now();
            let result = wait_for_empty_with_control(
                0,
                &receiver,
                &mut termination_requested,
                &mut control_error,
                &mut termination_error,
                started,
            );
            let error = result.expect_err("failed termination must be terminal");
            assert_eq!(error.kind(), io::ErrorKind::PermissionDenied);
            assert!(started.elapsed() < Duration::from_millis(100));

            let status = status_json(&StatusSnapshot {
                state: "error",
                token: "77777777-7777-4777-8777-777777777777",
                host_pid: 123,
                target_pid: Some(456),
                exit_code: None,
                quiesced: false,
                ready_acknowledged: true,
                reason: Some(&error.to_string()),
            });
            assert!(status.contains("\"state\":\"error\""));
            assert!(status.contains("\"quiesced\":false"));
        }
    }
}

#[cfg(windows)]
fn main() {
    std::process::exit(windows_host::entry());
}
