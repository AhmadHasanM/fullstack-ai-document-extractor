import asyncio
import threading
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from src.api.routes import router
from src.services.queue_consumer import QueueConsumer
from src.config import settings
from src.database.db import Database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

queue_consumer = None
consumer_thread = None
stop_event = threading.Event()
db = None


def run_consumer():
    """Run RabbitMQ consumer safely in thread"""
    global queue_consumer

    print("🎯 Starting RabbitMQ consumer thread...")

    try:
        queue_consumer = QueueConsumer()
        queue_consumer.connect()

        # blocking loop
        queue_consumer.start()

    except Exception as e:
        print(f"❌ Consumer thread error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global consumer_thread, queue_consumer, db

    print("🚀 Starting AI Service...")
    print(f"📁 Outputs directory: {settings.OUTPUTS_DIR}")
    print(f"🔗 RabbitMQ URL: {settings.RABBITMQ_URL}")
    print(f"📬 Queue Name: {settings.QUEUE_NAME}")

    # Initialize and connect database (creates tables if not exist)
    print("📊 Connecting to database...")
    db = Database()
    await db.connect()
    print("✅ Database connected and tables ready")

    # Start consumer thread
    consumer_thread = threading.Thread(
        target=run_consumer,
        daemon=True,
        name="RabbitMQ-Consumer"
    )
    consumer_thread.start()

    # wait small delay to ensure connection
    await asyncio.sleep(2)

    print("✅ AI Service started successfully")
    print("👂 Consumer is listening for messages...")

    yield

    # ======================
    # SHUTDOWN CLEANLY
    # ======================
    print("🛑 Shutting down AI Service...")

    try:
        if db:
            await db.close()
            print("✅ Database connection closed")

        if queue_consumer:
            if hasattr(queue_consumer, "stop"):
                queue_consumer.stop()
            else:
                if queue_consumer.connection:
                    queue_consumer.connection.close()

    except Exception as e:
        print(f"⚠️ Shutdown error: {e}")

    print("✅ AI Service shutdown complete")


app = FastAPI(
    title="PDF Extractor AI Service",
    description="AI-powered PDF extraction service",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "service": "PDF Extractor AI Service",
        "status": "running",
        "version": "1.0.0",
        "consumer_active": consumer_thread.is_alive() if consumer_thread else False
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "consumer_status": (
            "running"
            if consumer_thread and consumer_thread.is_alive()
            else "stopped"
        )
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )