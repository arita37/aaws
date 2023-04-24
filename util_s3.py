""""

Atomic and concurrent write on S3


"""

import boto3
from botocore.exceptions import ClientError



def test(): 
    
   s3lock= S3FileLock(_ 
   data = b'some data to write'
   s3lock.atomic_write(data)

    
import boto3
from botocore.exceptions import ClientError

class S3FileLock:
    def __init__(self, bucket_name, key):
        self.s3 = boto3.client('s3')
        self.bucket_name = bucket_name
        self.key = key
        self.lock_key = f"{key}.lock"

    def acquire_lock(self):
        try:
            self.s3.head_object(Bucket=self.bucket_name, Key=self.lock_key)
            return False
        except ClientError:
            self.s3.put_object(Bucket=self.bucket_name, Key=self.lock_key)
            return True

    def release_lock(self):
        self.s3.delete_object(Bucket=self.bucket_name, Key=self.lock_key)

    def atomic_write(self, data):
        if not self.acquire_lock():
            raise Exception("Failed to acquire lock")
        try:
            self.s3.put_object(Body=data, Bucket=self.bucket_name, Key=self.key)
        finally:
            self.release_lock()
    
    
  
  
