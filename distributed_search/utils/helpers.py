"""
Utility functions for distributed search engine
"""
import os
import hashlib
import time
import mimetypes
from typing import Dict, Any, List, Optional
import psutil


def get_file_hash(file_path: str, algorithm: str = 'md5') -> str:
    """
    Calculate hash of a file
    
    Args:
        file_path: Path to the file
        algorithm: Hashing algorithm ('md5', 'sha1', 'sha256')
        
    Returns:
        Hexadecimal hash string
    """
    hash_func = getattr(hashlib, algorithm)()
    
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_func.update(chunk)
        return hash_func.hexdigest()
    except (IOError, OSError):
        return ""


def get_file_info(file_path: str) -> Dict[str, Any]:
    """
    Get comprehensive file information
    
    Args:
        file_path: Path to the file
        
    Returns:
        Dictionary with file information
    """
    if not os.path.exists(file_path):
        return {}
        
    try:
        stat = os.stat(file_path)
        mime_type, _ = mimetypes.guess_type(file_path)
        
        return {
            "file_path": file_path,
            "file_name": os.path.basename(file_path),
            "file_size": stat.st_size,
            "created_time": stat.st_ctime,
            "modified_time": stat.st_mtime,
            "accessed_time": stat.st_atime,
            "mime_type": mime_type,
            "extension": os.path.splitext(file_path)[1].lower(),
            "is_readable": os.access(file_path, os.R_OK),
            "is_writable": os.access(file_path, os.W_OK),
            "permissions": oct(stat.st_mode)[-3:]
        }
    except (IOError, OSError):
        return {}


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human readable format
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted size string
    """
    if size_bytes == 0:
        return "0 B"
        
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
        
    return f"{size_bytes:.1f} {size_names[i]}"


def format_time_ago(timestamp: float) -> str:
    """
    Format timestamp as time ago
    
    Args:
        timestamp: Unix timestamp
        
    Returns:
        Human readable time ago string
    """
    now = time.time()
    diff = now - timestamp
    
    if diff < 60:
        return f"{int(diff)} seconds ago"
    elif diff < 3600:
        return f"{int(diff / 60)} minutes ago"
    elif diff < 86400:
        return f"{int(diff / 3600)} hours ago"
    else:
        return f"{int(diff / 86400)} days ago"


def get_system_info() -> Dict[str, Any]:
    """
    Get system information
    
    Returns:
        Dictionary with system information
    """
    return {
        "cpu_count": psutil.cpu_count(),
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory": {
            "total": psutil.virtual_memory().total,
            "available": psutil.virtual_memory().available,
            "percent": psutil.virtual_memory().percent
        },
        "disk": {
            "total": psutil.disk_usage('/').total,
            "free": psutil.disk_usage('/').free,
            "percent": psutil.disk_usage('/').percent
        },
        "load_average": os.getloadavg() if hasattr(os, 'getloadavg') else [0, 0, 0]
    }


def validate_directory(directory: str) -> bool:
    """
    Validate if directory exists and is accessible
    
    Args:
        directory: Directory path to validate
        
    Returns:
        True if directory is valid, False otherwise
    """
    return (
        os.path.exists(directory) and 
        os.path.isdir(directory) and 
        os.access(directory, os.R_OK)
    )


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename for safe file operations
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    # Remove/replace unsafe characters
    unsafe_chars = '<>:"/\\|?*'
    for char in unsafe_chars:
        filename = filename.replace(char, '_')
        
    # Remove leading/trailing dots and spaces
    filename = filename.strip('. ')
    
    # Ensure filename is not empty
    if not filename:
        filename = "unnamed_file"
        
    return filename


def is_text_file(file_path: str) -> bool:
    """
    Check if file is likely a text file
    
    Args:
        file_path: Path to the file
        
    Returns:
        True if file appears to be text, False otherwise
    """
    text_extensions = {
        '.txt', '.md', '.py', '.js', '.html', '.css', '.json', '.xml',
        '.yml', '.yaml', '.ini', '.cfg', '.conf', '.log', '.csv',
        '.sql', '.sh', '.bat', '.ps1', '.rb', '.php', '.java',
        '.cpp', '.c', '.h', '.go', '.rs', '.swift', '.kt'
    }
    
    _, ext = os.path.splitext(file_path)
    if ext.lower() in text_extensions:
        return True
        
    # Try to read a small portion to check if it's text
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(512)
            # Check for null bytes (binary indicator)
            return b'\x00' not in chunk
    except (IOError, OSError):
        return False


def create_file_index(directories: List[str]) -> Dict[str, Any]:
    """
    Create an index of files in directories
    
    Args:
        directories: List of directories to index
        
    Returns:
        Dictionary with file index information
    """
    index = {
        "created_at": time.time(),
        "directories": directories,
        "files": [],
        "stats": {
            "total_files": 0,
            "total_size": 0,
            "file_types": {},
            "directories_processed": 0
        }
    }
    
    for directory in directories:
        if not validate_directory(directory):
            continue
            
        index["stats"]["directories_processed"] += 1
        
        for root, dirs, files in os.walk(directory):
            for file in files:
                file_path = os.path.join(root, file)
                file_info = get_file_info(file_path)
                
                if file_info:
                    index["files"].append(file_info)
                    index["stats"]["total_files"] += 1
                    index["stats"]["total_size"] += file_info.get("file_size", 0)
                    
                    ext = file_info.get("extension", "")
                    index["stats"]["file_types"][ext] = index["stats"]["file_types"].get(ext, 0) + 1
                    
    return index


def filter_files_by_type(files: List[Dict[str, Any]], file_types: List[str]) -> List[Dict[str, Any]]:
    """
    Filter files by file types
    
    Args:
        files: List of file information dictionaries
        file_types: List of allowed file extensions
        
    Returns:
        Filtered list of files
    """
    if not file_types:
        return files
        
    file_types_lower = [ft.lower() for ft in file_types]
    return [
        file_info for file_info in files
        if file_info.get("extension", "").lower() in file_types_lower
    ]


def get_network_interfaces() -> List[Dict[str, str]]:
    """
    Get network interface information
    
    Returns:
        List of network interfaces with their IP addresses
    """
    interfaces = []
    
    try:
        for interface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == 2:  # IPv4
                    interfaces.append({
                        "interface": interface,
                        "ip": addr.address,
                        "netmask": addr.netmask
                    })
    except Exception:
        pass
        
    return interfaces