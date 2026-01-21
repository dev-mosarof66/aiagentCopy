"""Service for file-based RAG (Retrieval-Augmented Generation) without a database."""
import os
import pandas as pd
import logging
from typing import List, Dict, Any, Optional
from app.config import settings

logger = logging.getLogger(__name__)

class RAGService:
    """Service for managing file-based context retrieval without ChromaDB."""
    
    def __init__(self):
        """Initialize RAG service."""
        self.uploads_dir = settings.UPLOADS_DIR
        # Cache for loaded data to avoid re-reading files on every query
        self.data_cache: Dict[str, Any] = {}
        logger.info("RAG Service initialized in file-based mode (no database)")

    def _get_all_files(self) -> List[str]:
        """Get list of all supported files in the uploads directory."""
        if not os.path.exists(self.uploads_dir):
            return []
        return [f for f in os.listdir(self.uploads_dir) if os.path.isfile(os.path.join(self.uploads_dir, f))]

    def query(self, query_text: str) -> str:
        """
        Query the uploaded files directly for relevant information.
        
        Args:
            query_text: The search query
            
        Returns:
            Concatenated string of relevant information from files
        """
        try:
            files = self._get_all_files()
            if not files:
                return ""

            context_parts = []
            query_words = query_text.lower().split()
            
            for file_name in files:
                file_path = os.path.join(self.uploads_dir, file_name)
                file_ext = os.path.splitext(file_name)[1].lower()
                
                # Logic for Excel files
                if file_ext in [".xlsx", ".xls"]:
                    try:
                        # Use cache or load
                        if file_name not in self.data_cache:
                            self.data_cache[file_name] = pd.read_excel(file_path)
                        
                        df = self.data_cache[file_name]
                        
                        # Simple keyword filtering for relevant rows
                        # We look for rows where any column contains any of the query words
                        relevant_rows = []
                        for _, row in df.iterrows():
                            row_str = " ".join(map(str, row.values)).lower()
                            if any(word in row_str for word in query_words):
                                content = " | ".join([f"{col}: {val}" for col, val in row.items()])
                                relevant_rows.append(content)
                        
                        if relevant_rows:
                            # Limit to top 10 relevant rows for context length
                            context_parts.append(f"[Source: {file_name} (Excel)]\n" + "\n".join(relevant_rows[:10]))
                    except Exception as e:
                        logger.error(f"Error reading Excel {file_name}: {str(e)}")

                # Logic for text files
                elif file_ext in [".txt", ".md"]:
                    try:
                        # Use cache or load
                        if file_name not in self.data_cache:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                self.data_cache[file_name] = f.read()
                        
                        content = self.data_cache[file_name]
                        
                        # If query matches anything in the text, include relevant paragraphs
                        paragraphs = content.split('\n\n')
                        relevant_paras = []
                        for para in paragraphs:
                            if any(word in para.lower() for word in query_words):
                                relevant_paras.append(para.strip())
                        
                        if relevant_paras:
                            # Limit to top 5 relevant paragraphs
                            context_parts.append(f"[Source: {file_name} (Document)]\n" + "\n\n".join(relevant_paras[:5]))
                        elif len(content) < 2000: # If file is small, just include the whole thing as fallback
                            context_parts.append(f"[Source: {file_name}]\n{content}")
                            
                    except Exception as e:
                        logger.error(f"Error reading text file {file_name}: {str(e)}")

            return "\n\n---\n\n".join(context_parts) if context_parts else ""
            
        except Exception as e:
            logger.error(f"Error in file-based query: {str(e)}", exc_info=True)
            return ""

    def clear_cache(self):
        """Clear the in-memory data cache."""
        self.data_cache = {}

# Lazy global instance
_rag_service_instance = None

def get_rag_service() -> RAGService:
    """Get or create RAG service instance (lazy initialization)."""
    global _rag_service_instance
    if _rag_service_instance is None:
        _rag_service_instance = RAGService()
    return _rag_service_instance
