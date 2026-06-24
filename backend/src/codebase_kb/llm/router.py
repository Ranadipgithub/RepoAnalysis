import os
from cryptography.fernet import Fernet
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint

def _get_cipher():
    key = os.getenv("APP_SECRET_KEY")
    if not key:
        raise RuntimeError("APP_SECRET_KEY not set")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError):
        # User provided a raw 32-byte string; derive a Fernet key from it
        import base64, hashlib
        derived = base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest())
        return Fernet(derived)

cipher_suite = _get_cipher()

async def get_provider_for_user(user_id: str, requested_provider: str, db_session):
    """
    Fetches the individual user's API key for a specific provider, decrypts it, 
    and returns a configured LangChain ChatModel.
    """
    
    # 2. Fetch the specific user's key for the explicitly requested provider
    query = """
        SELECT encrypted_key, model 
        FROM api_keys 
        WHERE user_id = :user_id 
          AND provider = :requested_provider
        ORDER BY created_at DESC 
        LIMIT 1
    """
    row = await db_session.execute(query, {
        "user_id": user_id,
        "requested_provider": requested_provider
    })
    result = row.fetchone()

    if not result:
        raise ValueError(f"User {user_id} has no API key configured for {requested_provider}.")

    encrypted_key = result.encrypted_key
    model_name = result.model

    # 3. Decrypt the key using Fernet
    decrypted_key = cipher_suite.decrypt(encrypted_key.encode()).decode()

    # 4. Instantiate the LangChain model directly with the decrypted key
    if requested_provider == "anthropic":
        return ChatAnthropic(
            model=model_name, 
            api_key=decrypted_key, 
            temperature=0.2
        )
        
    elif requested_provider == "gemini":
        return ChatGoogleGenerativeAI(
            model=model_name, 
            google_api_key=decrypted_key, 
            temperature=0.2
        )
        
    elif requested_provider == "openai":
        return ChatOpenAI(
            model=model_name,
            api_key=decrypted_key,
            temperature=0.2
        )
        
    elif requested_provider == "huggingface":
        # Connect to the Hugging Face endpoint first, then wrap it in ChatHuggingFace
        llm_endpoint = HuggingFaceEndpoint(
            repo_id=model_name, 
            huggingfacehub_api_token=decrypted_key,
            temperature=0.2,
            task="text-generation"
        )
        return ChatHuggingFace(llm=llm_endpoint)
        
    else:
        raise ValueError(f"Unsupported LLM provider: {requested_provider}")