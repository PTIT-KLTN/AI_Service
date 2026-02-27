"""
Pinecone Knowledge Base Service - Alternative to AWS Bedrock KB
Uses free sentence-transformers for embeddings and Pinecone for vector search
"""
import os
import json
import logging
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from pinecone import Pinecone
from sentence_transformers import SentenceTransformer

load_dotenv()
logger = logging.getLogger(__name__)


class PineconeKBService:
    """
    Vector search service using Pinecone and free embedding models
    Bypass AWS Bedrock throttling by using external vector DB
    """
    
    def __init__(self):
        # Pinecone config
        self.api_key = os.getenv("PINECONE_API_KEY")
        self.index_name = os.getenv("PINECONE_INDEX_NAME", "recipe-kb")
        self.namespace = os.getenv("PINECONE_NAMESPACE", "dishes")
        
        if not self.api_key:
            raise ValueError("PINECONE_API_KEY not found in environment variables")
        
        # Initialize Pinecone (v3+ API)
        self.pc = Pinecone(api_key=self.api_key)
        self.index = self.pc.Index(self.index_name)
        
        # Load embedding model
        # Using intfloat/multilingual-e5-large (dimension=1024, multilingual support)
        self.embedding_model_name = os.getenv(
            "EMBEDDING_MODEL", 
            "intfloat/multilingual-e5-large"
        )
        
        logger.info(f"Loading embedding model: {self.embedding_model_name}")
        self.embedding_model = SentenceTransformer(self.embedding_model_name)
        logger.info(f"Embedding model loaded. Dimension: {self.embedding_model.get_sentence_embedding_dimension()}")
    
    def _embed_query(self, query: str) -> List[float]:
        """
        Generate embedding vector for query text
        Note: For multilingual-e5 models, we need to add 'query: ' prefix
        """
        # Add prefix for e5 models (improves performance)
        prefixed_query = f"query: {query}"
        embedding = self.embedding_model.encode(prefixed_query, convert_to_tensor=False, normalize_embeddings=True)
        return embedding.tolist()
    
    def search_dishes(
        self, 
        query: str, 
        top_k: int = 5,
        filter_dict: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for dishes in Pinecone vector DB
        
        Args:
            query: Search query text (e.g., "canh chua cá lóc")
            top_k: Number of results to return
            filter_dict: Metadata filters (e.g., {"category": "mon canh"})
        
        Returns:
            List of matching documents with metadata
        """
        try:
            # Generate query embedding
            query_vector = self._embed_query(query)
            
            # Search in Pinecone (following official docs v8+ API)
            query_params = {
                "namespace": self.namespace,
                "vector": query_vector,
                "top_k": top_k,
                "include_metadata": True,
                "include_values": False  # For better performance
            }
            
            # Add filter if provided
            if filter_dict:
                query_params["filter"] = filter_dict
            
            results = self.index.query(**query_params)
            
            # Extract matches (response format: {'matches': [...], 'namespace': '...', 'usage': {...}})
            matches = []
            for match in results.get('matches', []):
                matches.append({
                    'id': match.get('id'),
                    'score': match.get('score'),
                    'metadata': match.get('metadata', {})
                })
            
            logger.info(f"Found {len(matches)} matches for query: {query} (read_units: {results.get('usage', {}).get('read_units', 'N/A')})")
            return matches
            
        except Exception as e:
            logger.error(f"Error searching Pinecone: {e}")
            return []
    
    def build_context_from_matches(self, matches: List[Dict]) -> str:
        """
        Build context string from Pinecone search results
        Used for RAG with LLM
        """
        context_parts = []
        
        for idx, match in enumerate(matches, 1):
            metadata = match['metadata']
            name_vi = metadata.get('name_vi', '')
            
            # Format ingredients
            ing_lines = []
            ingredients_str = metadata.get('ingredients', '[]')
            
            try:
                ingredients = json.loads(ingredients_str) if isinstance(ingredients_str, str) else ingredients_str
                
                for ing in ingredients:
                    if isinstance(ing, dict):
                        ing_name_vi = ing.get('name_vi', '')
                        ing_name_en = ing.get('name_en', '')
                        quantity = ing.get('quantity', '')
                        unit = ing.get('unit', '')
                        
                        ing_str = f"- {ing_name_vi}"
                        if ing_name_en:
                            ing_str += f" ({ing_name_en})"
                        if quantity and unit:
                            ing_str += f": {quantity} {unit}"
                        
                        ing_lines.append(ing_str)
            except Exception as e:
                logger.error(f"Error formatting ingredients: {e}")
            
            context = f"[Tài liệu {idx}]:\nMón: {name_vi}\nĐiểm tương đồng: {match['score']:.2f}\nNguyên liệu:\n" + "\n".join(ing_lines)
            context_parts.append(context)
        
        return "\n\n".join(context_parts)
