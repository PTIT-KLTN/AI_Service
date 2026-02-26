import json
import os
import sys
from typing import Dict, Iterable, List, Optional, Tuple

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from tqdm import tqdm


DOC_TYPE_BY_PREFIX = {
    "dishes/": "dish",
    "ingredients/": "ingredient",
}


def _detect_doc_type_from_key(key: str) -> Optional[str]:
    for prefix, doc_type in DOC_TYPE_BY_PREFIX.items():
        if key.startswith(prefix):
            return doc_type
    return None


def _iter_keys(s3, bucket: str, prefix: str) -> Iterable[str]:
    """Iterate all object keys under a prefix (handles pagination)."""
    continuation_token: Optional[str] = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token

        resp = s3.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []):
            yield obj["Key"]

        if resp.get("IsTruncated"):
            continuation_token = resp.get("NextContinuationToken")
        else:
            break


class S3Uploader:
    def __init__(self, bucket_name: str):
        self.bucket_name = bucket_name
        self.s3 = boto3.client("s3")

    def upload_json_with_metadata(self, key: str, data: Dict, doc_type: str):
        """Upload JSON file and corresponding metadata file (theo code mẫu)."""

        self.s3.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=json.dumps(data, ensure_ascii=False),
            ContentType="application/json",
        )

        metadata = {"metadataAttributes": {"type": doc_type}}
        metadata_key = f"{key}.metadata.json"
        self.s3.put_object(
            Bucket=self.bucket_name,
            Key=metadata_key,
            Body=json.dumps(metadata),
            ContentType="application/json",
        )

    def upload_metadata_sidecar(
        self,
        key: str,
        doc_type: str,
        *,
        overwrite: bool,
        dry_run: bool,
    ) -> Tuple[bool, str]:
        """Chỉ tạo/ghi file metadata sidecar cho object key."""

        metadata_key = f"{key}.metadata.json"
        if not overwrite:
            try:
                self.s3.head_object(Bucket=self.bucket_name, Key=metadata_key)
                return True, "skipped_exists"
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code")
                if code not in {"404", "NoSuchKey", "NotFound"}:
                    return False, f"head_metadata_failed: {code}"

        if dry_run:
            return True, "dry_run"

        metadata = {"metadataAttributes": {"type": doc_type}}
        try:
            self.s3.put_object(
                Bucket=self.bucket_name,
                Key=metadata_key,
                Body=json.dumps(metadata),
                ContentType="application/json",
            )
            return True, "written"
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "ClientError")
            msg = e.response.get("Error", {}).get("Message", str(e))
            return False, f"{code}: {msg}"


def main() -> None:
    dry_run = "--dry-run" in sys.argv or "--test" in sys.argv
    overwrite = "--overwrite" in sys.argv

    bucket = "recipe-dishes"
    prefixes = list(DOC_TYPE_BY_PREFIX.keys())

    print("\n" + "=" * 70)
    print("🔧 S3 Metadata Sidecar Generator")
    print("=" * 70)
    print(f"📦 Bucket: {bucket}")
    print(f"📁 Prefixes: {', '.join(prefixes)}")
    if dry_run:
        print("⚠️  DRY RUN MODE - Không ghi lên S3")
    if overwrite:
        print("♻️  OVERWRITE - Ghi đè *.metadata.json nếu đã tồn tại")
    print()

    s3 = boto3.client("s3")
    keys: List[str] = []
    try:
        for prefix in prefixes:
            count = 0
            for k in _iter_keys(s3, bucket, prefix):
                if not k.endswith(".json"):
                    continue
                if k.endswith(".metadata.json"):
                    continue
                keys.append(k)
                count += 1
            print(f"📂 {prefix}: {count} json files")
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "ClientError")
        msg = e.response.get("Error", {}).get("Message", str(e))
        print(f"❌ Lỗi khi liệt kê files: {code}: {msg}")
        sys.exit(1)

    if not keys:
        print("⚠️  Không tìm thấy file JSON nào trong 2 folder.")
        return

    print(f"\n📄 Tổng cộng: {len(keys)} file(s)\n")

    uploader = S3Uploader(bucket)
    results = {"success": 0, "failed": 0, "skipped": 0}
    first_error: Optional[Tuple[str, str]] = None

    for key in tqdm(keys, desc="Processing", unit="file", ncols=70):
        doc_type = _detect_doc_type_from_key(key)
        if not doc_type:
            results["skipped"] += 1
            continue

        ok, status = uploader.upload_metadata_sidecar(
            key,
            doc_type,
            overwrite=overwrite,
            dry_run=dry_run,
        )

        if ok and status == "skipped_exists":
            results["skipped"] += 1
        elif ok:
            results["success"] += 1
        else:
            results["failed"] += 1
            if first_error is None:
                first_error = (key, status)

    print("\n" + "=" * 70)
    print("📊 KẾT QUẢ")
    print("=" * 70)
    print(f"✅ Thành công: {results['success']}")
    print(f"❌ Thất bại:   {results['failed']}")
    print(f"⏭️  Bỏ qua:    {results['skipped']}")
    if first_error:
        print("-" * 70)
        print(f"Ví dụ lỗi đầu tiên: {first_error[0]}")
        print(f"Lý do: {first_error[1]}")
    print("=" * 70)
    if dry_run:
        print("💡 Chạy lại không có --dry-run để thực hiện thay đổi")
    else:
        print("✅ Hoàn thành! Nhớ sync lại Bedrock Knowledge Base")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
