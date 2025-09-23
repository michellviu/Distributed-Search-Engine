"""
File indexing system for distributed search engine
"""
import json
import os
import time
import sqlite3
from typing import Dict, List, Any, Optional
from distributed_search.utils.helpers import get_file_info, get_file_hash


class FileIndex:
    """
    File indexing system for efficient search operations
    """
    
    def __init__(self, index_file: str = None):
        self.index_file = index_file or "file_index.db"
        self.connection = None
        self.init_database()
        
    def init_database(self):
        """Initialize SQLite database for file index"""
        self.connection = sqlite3.connect(self.index_file)
        self.connection.row_factory = sqlite3.Row
        
        cursor = self.connection.cursor()
        
        # Create tables
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT UNIQUE NOT NULL,
                file_name TEXT NOT NULL,
                file_size INTEGER,
                file_hash TEXT,
                mime_type TEXT,
                extension TEXT,
                created_time REAL,
                modified_time REAL,
                indexed_time REAL,
                node_id TEXT,
                is_accessible BOOLEAN DEFAULT 1
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS file_content (
                file_id INTEGER PRIMARY KEY,
                content TEXT,
                content_hash TEXT,
                extracted_time REAL,
                FOREIGN KEY (file_id) REFERENCES files (id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS search_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern TEXT NOT NULL,
                search_type TEXT NOT NULL,
                results TEXT,
                created_time REAL,
                expires_time REAL
            )
        ''')
        
        # Create indexes for performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_file_name ON files (file_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_file_extension ON files (extension)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_modified_time ON files (modified_time)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_node_id ON files (node_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_search_pattern ON search_cache (pattern, search_type)')
        
        self.connection.commit()
        
    def add_file(self, file_path: str, node_id: str = None) -> bool:
        """
        Add file to index
        
        Args:
            file_path: Path to the file
            node_id: ID of the node containing the file
            
        Returns:
            True if file was added successfully, False otherwise
        """
        if not os.path.exists(file_path):
            return False
            
        file_info = get_file_info(file_path)
        if not file_info:
            return False
            
        cursor = self.connection.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO files (
                    file_path, file_name, file_size, file_hash, mime_type,
                    extension, created_time, modified_time, indexed_time, node_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                file_info['file_path'],
                file_info['file_name'],
                file_info['file_size'],
                get_file_hash(file_path),
                file_info.get('mime_type'),
                file_info['extension'],
                file_info['created_time'],
                file_info['modified_time'],
                time.time(),
                node_id
            ))
            
            self.connection.commit()
            return True
            
        except sqlite3.Error as e:
            print(f"Error adding file to index: {e}")
            return False
            
    def remove_file(self, file_path: str) -> bool:
        """
        Remove file from index
        
        Args:
            file_path: Path to the file
            
        Returns:
            True if file was removed successfully, False otherwise
        """
        cursor = self.connection.cursor()
        
        try:
            # Get file ID first
            cursor.execute('SELECT id FROM files WHERE file_path = ?', (file_path,))
            row = cursor.fetchone()
            
            if row:
                file_id = row['id']
                
                # Remove from content table
                cursor.execute('DELETE FROM file_content WHERE file_id = ?', (file_id,))
                
                # Remove from files table
                cursor.execute('DELETE FROM files WHERE id = ?', (file_id,))
                
                self.connection.commit()
                return True
                
        except sqlite3.Error as e:
            print(f"Error removing file from index: {e}")
            
        return False
        
    def update_file_content(self, file_path: str, content: str) -> bool:
        """
        Update file content in index
        
        Args:
            file_path: Path to the file
            content: File content
            
        Returns:
            True if content was updated successfully, False otherwise
        """
        cursor = self.connection.cursor()
        
        try:
            # Get file ID
            cursor.execute('SELECT id FROM files WHERE file_path = ?', (file_path,))
            row = cursor.fetchone()
            
            if not row:
                return False
                
            file_id = row['id']
            content_hash = get_file_hash(file_path)
            
            cursor.execute('''
                INSERT OR REPLACE INTO file_content (
                    file_id, content, content_hash, extracted_time
                ) VALUES (?, ?, ?, ?)
            ''', (file_id, content, content_hash, time.time()))
            
            self.connection.commit()
            return True
            
        except sqlite3.Error as e:
            print(f"Error updating file content: {e}")
            return False
            
    def search_files(self, pattern: str, search_type: str = 'filename', limit: int = 100) -> List[Dict[str, Any]]:
        """
        Search files in index
        
        Args:
            pattern: Search pattern
            search_type: Type of search ('filename', 'content', 'extension')
            limit: Maximum number of results
            
        Returns:
            List of matching files
        """
        cursor = self.connection.cursor()
        results = []
        
        try:
            if search_type == 'filename':
                cursor.execute('''
                    SELECT * FROM files 
                    WHERE file_name LIKE ? AND is_accessible = 1
                    ORDER BY modified_time DESC
                    LIMIT ?
                ''', (f'%{pattern}%', limit))
                
            elif search_type == 'extension':
                cursor.execute('''
                    SELECT * FROM files 
                    WHERE extension LIKE ? AND is_accessible = 1
                    ORDER BY modified_time DESC
                    LIMIT ?
                ''', (f'%{pattern}%', limit))
                
            elif search_type == 'content':
                cursor.execute('''
                    SELECT f.* FROM files f
                    JOIN file_content fc ON f.id = fc.file_id
                    WHERE fc.content LIKE ? AND f.is_accessible = 1
                    ORDER BY f.modified_time DESC
                    LIMIT ?
                ''', (f'%{pattern}%', limit))
                
            rows = cursor.fetchall()
            results = [dict(row) for row in rows]
            
        except sqlite3.Error as e:
            print(f"Error searching files: {e}")
            
        return results
        
    def get_file_stats(self) -> Dict[str, Any]:
        """
        Get file index statistics
        
        Returns:
            Dictionary with statistics
        """
        cursor = self.connection.cursor()
        stats = {}
        
        try:
            # Total files
            cursor.execute('SELECT COUNT(*) as count FROM files WHERE is_accessible = 1')
            stats['total_files'] = cursor.fetchone()['count']
            
            # Total size
            cursor.execute('SELECT SUM(file_size) as total_size FROM files WHERE is_accessible = 1')
            stats['total_size'] = cursor.fetchone()['total_size'] or 0
            
            # Files by extension
            cursor.execute('''
                SELECT extension, COUNT(*) as count 
                FROM files 
                WHERE is_accessible = 1 
                GROUP BY extension 
                ORDER BY count DESC
            ''')
            stats['files_by_extension'] = {row['extension']: row['count'] for row in cursor.fetchall()}
            
            # Files by node
            cursor.execute('''
                SELECT node_id, COUNT(*) as count 
                FROM files 
                WHERE is_accessible = 1 
                GROUP BY node_id 
                ORDER BY count DESC
            ''')
            stats['files_by_node'] = {row['node_id']: row['count'] for row in cursor.fetchall()}
            
            # Recently modified files
            cursor.execute('''
                SELECT * FROM files 
                WHERE is_accessible = 1 
                ORDER BY modified_time DESC 
                LIMIT 10
            ''')
            stats['recent_files'] = [dict(row) for row in cursor.fetchall()]
            
        except sqlite3.Error as e:
            print(f"Error getting file stats: {e}")
            
        return stats
        
    def cleanup_stale_files(self, max_age_days: int = 30) -> int:
        """
        Clean up stale file entries
        
        Args:
            max_age_days: Maximum age in days for indexed files
            
        Returns:
            Number of files removed
        """
        cursor = self.connection.cursor()
        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
        
        try:
            # Mark files as inaccessible if they don't exist
            cursor.execute('SELECT id, file_path FROM files WHERE is_accessible = 1')
            rows = cursor.fetchall()
            
            removed_count = 0
            for row in rows:
                if not os.path.exists(row['file_path']):
                    cursor.execute('UPDATE files SET is_accessible = 0 WHERE id = ?', (row['id'],))
                    removed_count += 1
                    
            # Remove very old inaccessible files
            cursor.execute('''
                DELETE FROM files 
                WHERE is_accessible = 0 AND indexed_time < ?
            ''', (cutoff_time,))
            
            removed_count += cursor.rowcount
            self.connection.commit()
            
            return removed_count
            
        except sqlite3.Error as e:
            print(f"Error cleaning up stale files: {e}")
            return 0
            
    def reindex_directory(self, directory: str, node_id: str = None) -> int:
        """
        Reindex all files in a directory
        
        Args:
            directory: Directory to reindex
            node_id: ID of the node
            
        Returns:
            Number of files indexed
        """
        if not os.path.exists(directory):
            return 0
            
        indexed_count = 0
        
        for root, dirs, files in os.walk(directory):
            for file in files:
                file_path = os.path.join(root, file)
                if self.add_file(file_path, node_id):
                    indexed_count += 1
                    
        return indexed_count
        
    def close(self):
        """Close database connection"""
        if self.connection:
            self.connection.close()
            self.connection = None