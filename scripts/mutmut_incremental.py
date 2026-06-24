import subprocess
import sys
import xml.etree.ElementTree as ET

def get_changed_files():
    # Try to compare with origin/main, then main, then HEAD~1 as fallback
    for target in ["origin/main", "main", "HEAD~1"]:
        try:
            res = subprocess.run(
                ["git", "diff", "--name-only", target],
                capture_output=True,
                text=True,
                check=True
            )
            files = [f.strip() for f in res.stdout.splitlines() if f.strip()]
            # If we succeed and get files (even empty list if no changes), return them
            return files
        except subprocess.CalledProcessError:
            continue
    # Fallback to local git diff against HEAD
    try:
        res = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True,
            text=True,
            check=True
        )
        return [f.strip() for f in res.stdout.splitlines() if f.strip()]
    except subprocess.CalledProcessError:
        return []

def main():
    changed_files = get_changed_files()
    py_files = [f for f in changed_files if f.startswith("app/") and f.endswith(".py") and "tests/" not in f]
    
    if not py_files:
        print("No changed Python files found in app/. Skipping mutation testing.")
        sys.exit(0)
        
    paths_arg = ",".join(py_files)
    print(f"Running mutmut for modified files: {paths_arg}")
    
    # Run mutmut
    run_res = subprocess.run(
        ["mutmut", "run", f"--paths-to-mutate={paths_arg}"],
        check=False
    )
    
    # Generate and parse junit report
    print("Generating mutation report...")
    junit_res = subprocess.run(
        ["mutmut", "junit"],
        capture_output=True,
        text=True,
        check=False
    )
    
    if junit_res.returncode != 0:
        print("Failed to run 'mutmut junit'. Output:")
        print(junit_res.stderr)
        sys.exit(1)
        
    try:
        root = ET.fromstring(junit_res.stdout)
        tests = int(root.get("tests", 0))
        failures = int(root.get("failures", 0))
        errors = int(root.get("errors", 0))
        
        if tests == 0:
            print("No mutations were generated.")
            sys.exit(0)
            
        killed = tests - failures - errors
        score = killed / tests
        
        print("\n=== Mutation Testing Summary ===")
        print(f"Total Mutants: {tests}")
        print(f"Killed:        {killed}")
        print(f"Survived:      {failures}")
        print(f"Errors:        {errors}")
        print(f"Mutation Score: {score:.2%}")
        print("================================\n")
        
        if score < 0.80:
            print("ERROR: Mutation score is below the required 80% threshold!")
            sys.exit(1)
        else:
            print("SUCCESS: Mutation score meets the 80% threshold.")
            sys.exit(0)
    except Exception as e:
        print(f"Error parsing junit XML: {e}")
        print("Raw XML output:")
        print(junit_res.stdout)
        sys.exit(1)

if __name__ == "__main__":
    main()
