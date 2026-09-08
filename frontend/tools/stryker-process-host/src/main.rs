//! Small, dependency-free Windows process host for the Stryker runner.
//!
//! The Windows implementation creates the target suspended, assigns it to a
//! private Job Object with KILL_ON_JOB_CLOSE, and only resumes it after the
//! assignment succeeds.  The host owns the job handle for the complete target
//! lifetime.  Node controls cancellation through stdin and observes an
//! atomic, token-bound status file; no numeric PID is ever used for cleanup.

#![deny(unsafe_op_in_unsafe_fn)]

#[cfg(not(windows))]
fn main() {
    eprintln!("stryker-process-host is supported only on Windows");
    std::process::exit(78);
}

#[cfg(windows)]
mod windows_host {
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
        let mut restore_error = None;
        if let Err(error) = stdout.restore() {
            restore_error = Some(error);
        }
        if let Err(error) = stderr.restore() {
            if restore_error.is_none() {
                restore_error = Some(error);
            }
        }
        if created == 0 {
            return Err(last_error("CreateProcessW"));
        }
        if let Some(error) = restore_error {
            unsafe {
                TerminateProcess(info.process, 70);
                WaitForSingleObject(info.process, 5_000);
                // The process/thread handles are not wrapped in `OwnedProcess`
                // on this error path, so close both explicitly after the
                // suspended child has been terminated.  Otherwise a failed
                // std-handle restoration would leak one pair of kernel
                // handles per shard.
                CloseHandle(info.thread);
                CloseHandle(info.process);
            }
            return Err(error);
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

    fn wait_for_empty(job: Handle, started: Instant) -> io::Result<()> {
        loop {
            let active = active_processes(job)?;
            if active == 0 {
                return Ok(());
            }
            if started.elapsed() >= MAX_STATUS_WAIT {
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "job active-process count did not reach zero",
                ));
            }
            thread::sleep(POLL_INTERVAL);
        }
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

    fn poll_control(
        controls: &Receiver<ControlMessage>,
        job: Handle,
        termination_requested: &mut bool,
        control_error: &mut Option<io::Error>,
    ) {
        match controls.try_recv() {
            Ok(ControlMessage::Terminate | ControlMessage::Eof) if !*termination_requested => {
                *termination_requested = true;
                if let Err(error) = terminate_job(job, 143) {
                    *control_error = Some(error);
                }
            }
            Ok(ControlMessage::Invalid) => {
                *control_error = Some(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    "invalid control command",
                ));
                if !*termination_requested {
                    *termination_requested = true;
                    let _ = terminate_job(job, 70);
                }
            }
            Ok(_) => {}
            Err(TryRecvError::Empty) => {}
            Err(TryRecvError::Disconnected) => {
                if !*termination_requested {
                    *termination_requested = true;
                    let _ = terminate_job(job, 143);
                }
            }
        }
    }

    fn wait_for_empty_with_control(
        job: Handle,
        controls: &Receiver<ControlMessage>,
        termination_requested: &mut bool,
        control_error: &mut Option<io::Error>,
        started: Instant,
    ) -> io::Result<()> {
        loop {
            // Keep consuming the dedicated control pipe even after the host's
            // direct target has exited.  A normal target can leave detached
            // descendants in the Job Object; cancellation must still be able
            // to terminate those members instead of waiting for the watchdog.
            poll_control(controls, job, termination_requested, control_error);
            let active = active_processes(job)?;
            if active == 0 {
                return Ok(());
            }
            if started.elapsed() >= MAX_STATUS_WAIT {
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "job active-process count did not reach zero",
                ));
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
            unsafe {
                TerminateProcess(target.process, 70);
                WaitForSingleObject(target.process, 5_000);
            }
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
                    reason: Some(&error.to_string()),
                }),
            );
            return Err(error);
        }
        if unsafe { ResumeThread(target.thread) } == u32::MAX {
            let error = last_error("ResumeThread");
            let _ = terminate_job(job.0, 70);
            let _ = wait_for_empty(job.0, Instant::now());
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
                    reason: Some(&error.to_string()),
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
        loop {
            poll_control(
                &controls,
                job.0,
                &mut termination_requested,
                &mut control_error,
            );
            let target_state = unsafe { WaitForSingleObject(target.process, 0) };
            if target_state == WAIT_FAILED {
                let error = last_error("WaitForSingleObject target");
                let _ = terminate_job(job.0, 70);
                let _ = wait_for_empty(job.0, Instant::now());
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
            if target_state != WAIT_OBJECT_0 && target_state != WAIT_TIMEOUT {
                let error =
                    io::Error::other(format!("unexpected target wait result {target_state}"));
                let _ = terminate_job(job.0, 70);
                let _ = wait_for_empty(job.0, Instant::now());
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
            if target_state == WAIT_OBJECT_0 {
                break;
            }
            thread::sleep(POLL_INTERVAL);
        }
        let target_code = wait_for_process(target.process)?;
        let proof_started = Instant::now();
        let empty_result = wait_for_empty_with_control(
            job.0,
            &controls,
            &mut termination_requested,
            &mut control_error,
            proof_started,
        );
        if termination_requested {
            let result = control_error.or_else(|| empty_result.err());
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
                let termination = terminate_job(job.0, 70);
                let empty = wait_for_empty(job.0, Instant::now());
                let quiesced = termination.is_ok() && empty.is_ok();
                let reason = termination
                    .as_ref()
                    .err()
                    .or_else(|| empty.as_ref().err())
                    .map_or_else(|| error.to_string(), |failure| failure.to_string());
                let status_result = write_status(
                    &config.status,
                    &status_json(&StatusSnapshot {
                        state: "job_terminated",
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
}

#[cfg(windows)]
fn main() {
    std::process::exit(windows_host::entry());
}
