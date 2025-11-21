"""Memory manager using Chroma for semantic memory storage and retrieval."""

from datetime import datetime
from typing import List, Tuple, Optional
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_chroma import Chroma
from langchain_core.documents import Document
import chromadb


class MemoryManager:
    """Manages conversation memory using Chroma vector database."""

    def __init__(
        self,
        chroma_client: chromadb.HttpClient,
        collection_name: str,
        embeddings
    ):
        """Initialize the memory manager.

        Args:
            chroma_client: Chroma HTTP client instance
            collection_name: Name of the collection for memory storage
            embeddings: Embedding function to use
        """
        self.chroma_client = chroma_client
        self.collection_name = collection_name
        self.embeddings = embeddings
        
        # Initialize Chroma vector store
        self.vector_store = Chroma(
            client=chroma_client,
            collection_name=collection_name,
            embedding_function=embeddings
        )

    def save_turn(
        self,
        session_id: str,
        user_msg: str,
        assistant_msg: str,
        turn_id: int
    ):
        """Save a conversation turn to memory.

        Args:
            session_id: Unique session identifier
            user_msg: User message content
            assistant_msg: Assistant response content
            turn_id: Turn number in the conversation
        """
        timestamp = datetime.now().isoformat()
        
        # Create documents for user and assistant messages
        documents = [
            Document(
                page_content=user_msg,
                metadata={
                    "session_id": session_id,
                    "timestamp": timestamp,
                    "role": "user",
                    "turn_id": turn_id
                }
            ),
            Document(
                page_content=assistant_msg,
                metadata={
                    "session_id": session_id,
                    "timestamp": timestamp,
                    "role": "assistant",
                    "turn_id": turn_id
                }
            )
        ]
        
        # Add to vector store
        self.vector_store.add_documents(documents)

    def retrieve_relevant_memories(
        self,
        session_id: str,
        query: str,
        k: int = 5
    ) -> List[str]:
        """Retrieve semantically relevant memories from the session.

        Args:
            session_id: Session identifier to filter by
            query: Query text for semantic search
            k: Number of memories to retrieve

        Returns:
            List of relevant memory texts
        """
        # Build filter for the specific session
        filter_dict = {"session_id": session_id}
        
        # Perform similarity search
        results = self.vector_store.similarity_search(
            query=query,
            k=k,
            filter=filter_dict
        )
        
        # Extract and format results
        memories = []
        for doc in results:
            role = doc.metadata.get("role", "unknown")
            turn_id = doc.metadata.get("turn_id", "?")
            content = doc.page_content
            formatted = f"[Turn {turn_id} - {role}]: {content}"
            memories.append(formatted)
        
        return memories

    def get_session_history(
        self,
        session_id: str,
        limit: int = 10
    ) -> List[Tuple[str, str]]:
        """Get recent conversation history for a session.

        Args:
            session_id: Session identifier
            limit: Maximum number of turns to retrieve

        Returns:
            List of (user_msg, assistant_msg) tuples, ordered by turn_id
        """
        # Get the collection directly to query with filters
        collection = self.chroma_client.get_or_create_collection(
            name=self.collection_name
        )
        
        # Query all documents for this session
        results = collection.get(
            where={"session_id": session_id},
            include=["metadatas", "documents"]
        )
        
        if not results or not results.get("documents"):
            return []
        
        # Group by turn_id
        turns = {}
        for i, doc in enumerate(results["documents"]):
            metadata = results["metadatas"][i]
            turn_id = metadata.get("turn_id", 0)
            role = metadata.get("role", "unknown")
            
            if turn_id not in turns:
                turns[turn_id] = {}
            turns[turn_id][role] = doc
        
        # Convert to ordered list of tuples
        history = []
        for turn_id in sorted(turns.keys())[-limit:]:
            turn_data = turns[turn_id]
            user_msg = turn_data.get("user", "")
            assistant_msg = turn_data.get("assistant", "")
            if user_msg and assistant_msg:
                history.append((user_msg, assistant_msg))
        
        return history

    def clear_session(self, session_id: str):
        """Clear all memories for a specific session.

        Args:
            session_id: Session identifier to clear
        """
        collection = self.chroma_client.get_or_create_collection(
            name=self.collection_name
        )
        
        # Get all document IDs for this session
        results = collection.get(
            where={"session_id": session_id},
            include=["metadatas"]
        )
        
        if results and results.get("ids"):
            collection.delete(ids=results["ids"])
