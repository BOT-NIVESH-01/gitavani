import os
import chromadb
from chromadb.utils import embedding_functions

def seed_vector_database():
    print("Database Initializer: Initializing ChromaDB storage directory...")
    # Creates a persistent local folder called 'gita_vectordb' to store your data for free
    db_client = chromadb.PersistentClient(path="./gita_vectordb")
    
    # Use a built-in lightweight embedding function that runs entirely locally
    embedding_func = embedding_functions.DefaultEmbeddingFunction()
    
    # Create or fetch our collection
    collection = db_client.get_or_create_collection(
        name="bhagavad_gita",
        embedding_function=embedding_func
    )
    
    # Core reference dataset focusing on mental anxiety, stress, and duty
    gita_verses = [
        {
            "id": "gita_2_47",
            "text": "Chapter 2, Verse 47: You have a right to perform your prescribed duties, but you are not entitled to the fruits of your actions. Never consider yourself to be the cause of the results of your activities, nor be attached to inaction.",
            "metadata": {"chapter": 2, "verse": 47, "topic": "anxiety_results"}
        },
        {
            "id": "gita_6_35",
            "text": "Chapter 6, Verse 35: Lord Krishna said: O mighty-armed son of Kunti, the mind is undoubtedly restless and difficult to curb; but it can be controlled by constant practice (abhyasa) and by detachment (vairagya).",
            "metadata": {"chapter": 6, "verse": 35, "topic": "restless_mind"}
        },
        {
            "id": "gita_18_66",
            "text": "Chapter 18, Verse 66: Abandon all varieties of duties and beliefs, and simply surrender unto Me alone. I shall liberate you from all sinful reactions and fear; do not grieve or worry.",
            "metadata": {"chapter": 18, "verse": 66, "topic": "surrender_fear"}
        },
        {
            "id": "gita_2_14",
            "text": "Chapter 2, Verse 14: O son of Kunti, the contact between the senses and their objects gives rise to fleeting feelings of heat and cold, pleasure and pain. These are temporary and come and go like the winter and summer seasons. One must learn to tolerate them without being disturbed.",
            "metadata": {"chapter": 2, "verse": 14, "topic": "emotional_pain"}
        }
    ]
    
    # Prepare data arrays for bulk vector insertion
    documents = [verse["text"] for verse in gita_verses]
    ids = [verse["id"] for verse in gita_verses]
    metadatas = [verse["metadata"] for verse in gita_verses]
    
    print(f"Database Initializer: Embedding and uploading {len(documents)} core verses...")
    collection.upsert(documents=documents, ids=ids, metadatas=metadatas)
    print("✅ Success! Your Vector Database is fully seeded locally at ./gita_vectordb")

if __name__ == "__main__":
    seed_vector_database()