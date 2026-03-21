import datetime
import os
import shutil
import subprocess
import sys


def get_env(key, default=None):
    val = os.environ.get(key, default)
    if val is None:
        print(f"Error: Environment variable {key} is required.")
        sys.exit(1)
    return val


def run_backup():
    db_host = get_env("DB_HOST", "localhost")
    db_user = get_env("DB_USER")
    db_name = get_env("DB_NAME")
    pg_password = get_env("PGPASSWORD")

    minio_endpoint = os.environ.get("MINIO_ENDPOINT")
    minio_bucket = os.environ.get("MINIO_BUCKET", "backups")
    minio_access_key = os.environ.get("MINIO_ACCESS_KEY")
    minio_secret_key = os.environ.get("MINIO_SECRET_KEY")

    timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_{db_name}_{timestamp}.sql"
    backup_path = os.path.join(os.environ.get("TEMP", "/tmp"), backup_name)

    print(f"Starting backup for {db_name}...")

    # 1. Create SQL dump
    try:
        # Use subprocess to run pg_dump
        subprocess.run(
            ["pg_dump", "-h", db_host, "-U", db_user, "-f", backup_path, db_name],
            check=True,
            env={**os.environ, "PGPASSWORD": pg_password},
        )
        print(f"Backup created at {backup_path}")
    except subprocess.CalledProcessError as e:
        print(f"Error creating backup: {e}")
        sys.exit(1)

    # 2. Compress (optional but recommended, matching .sh behavior)
    compressed_path = f"{backup_path}.gz"
    import gzip

    with open(backup_path, "rb") as f_in, gzip.open(compressed_path, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)

    os.remove(backup_path)  # Remove uncompressed
    print(f"Compressed backup to {compressed_path}")

    # 3. Upload to MinIO (using boto3 if available, or 'mc' via subprocess)
    # Matching .sh behavior: preferring 'mc' if available
    try:
        if shutil.which("mc"):
            print("Using mc to upload...")
            subprocess.run(
                [
                    "mc",
                    "alias",
                    "set",
                    "myminio",
                    minio_endpoint,
                    minio_access_key,
                    minio_secret_key,
                ],
                check=True,
            )
            subprocess.run(
                [
                    "mc",
                    "cp",
                    compressed_path,
                    f"myminio/{minio_bucket}/backups/{os.path.basename(compressed_path)}",
                ],
                check=True,
            )
        else:
            print(
                "Error: Upload tool (mc) not found in path. "
                "Please install 'mc' or use boto3 integration."
            )
            sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Error during upload: {e}")
        sys.exit(1)

    # 4. Cleanup
    os.remove(compressed_path)
    print("Backup process complete.")


if __name__ == "__main__":
    run_backup()
