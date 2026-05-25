import os
from celery import Celery
import whisper
import ollama
import chromadb
from chromadb.utils import embedding_functions

celery_app = Celery(
    "tasks",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0"
)

print("Background Worker: Pre-loading Whisper base model...")
stt_model = whisper.load_model("base")

# Initialize persistent access to our local vector database
db_client = chromadb.PersistentClient(path="./gita_vectordb")
embedding_func = embedding_functions.DefaultEmbeddingFunction()
gita_collection = db_client.get_collection(name="bhagavad_gita", embedding_function=embedding_func)

@celery_app.task
def process_voice_async(input_audio_path: str, model_name: str):
    """
    Background task that transcribes voice, queries ChromaDB for contextual matching 
    Gita verses, and forces the local LLM to run an accurate RAG synthesis block.
    """
    try:
        if not os.path.exists(input_audio_path):
            return {"error": "Target audio file could not be found on disk."}
            
        print(f"Background Task: Processing audio -> {input_audio_path}")
        result = stt_model.transcribe(input_audio_path, fp16=False)
        user_text = result["text"].strip()
        print(f"Background Task: User said -> \"{user_text}\"")
        
        if not user_text:
            return {"error": "Audio appeared silent."}
            
        # ─── VECTOR DATABASE RAG INTERCEPTION ───
        print("Background Task: Scanning ChromaDB collection for semantic verse matches...")
        # Query database for the top 1 most relevant verse matching user's emotional state
        db_query = gita_collection.query(query_texts=[user_text], n_results=1)
        
        matched_verse = "No direct matching verse found."
        if db_query and db_query['documents'] and len(db_query['documents'][0]) > 0:
            matched_verse = db_query['documents'][0][0]
            print(f"Background Task: RAG Hit -> Match Found: {matched_verse[:50]}...")

        # Construct an explicit prompt template that injects the retrieved verse directly
        rag_enriched_prompt = f"""
Context from holy Bhagavad Gita text records:
{matched_verse}

User's current real-world emotional struggle:
"{user_text}"

Based strictly on the provided Bhagavad Gita Context, formulate a comforting first-person response as Lord Krishna. Comfort them, explain the eternal meaning of this exact verified verse, and guide them to peace. Do not use any markdown.
"""
        
        print(f"Background Task: Injecting RAG matrix frame down to [{model_name}]...")
        response = ollama.generate(model=model_name, prompt=rag_enriched_prompt)
        ai_reply = response["response"].strip()
        
        if os.path.exists(input_audio_path):
            os.remove(input_audio_path)
            
        return {
            "transcription": user_text,
            "reply": ai_reply
        }
        
    except Exception as worker_error:
        print(f"Background Task Error: {worker_error}")
        return {"error": str(worker_error)}