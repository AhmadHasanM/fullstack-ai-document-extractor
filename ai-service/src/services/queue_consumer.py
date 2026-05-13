import pika
import json
import asyncio
import threading
from typing import Dict, Any
from ..config import settings
from ..database.db import Database

class QueueConsumer:
    def __init__(self):
        self.connection = None
        self.channel = None
        self.db = Database()

    def connect(self):
        print("🔌 Connecting RabbitMQ...")
        params = pika.URLParameters(settings.RABBITMQ_URL)
        self.connection = pika.BlockingConnection(params)
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue=settings.QUEUE_NAME, durable=True)
        self.channel.basic_qos(prefetch_count=1)
        print("✅ RabbitMQ connected")

    def start_consuming(self):
        if not self.connection:
            self.connect()
        print("👂 Waiting for messages...")
        self.channel.basic_consume(
            queue=settings.QUEUE_NAME,
            on_message_callback=self.handle_message
        )
        self.channel.start_consuming()

    def handle_message(self, ch, method, properties, body):
        try:
            msg = json.loads(body.decode())
            print(f"\n📨 Received: {msg.get('document_id')}")

            # ACK dulu sebelum proses (sudah benar)
            ch.basic_ack(delivery_tag=method.delivery_tag)

            # ✅ Jalankan di thread terpisah, bukan asyncio.run() langsung
            thread = threading.Thread(
                target=self._run_in_thread,
                args=(msg,),
                daemon=True
            )
            thread.start()

        except Exception as e:
            print(f"❌ Error handling message: {e}")

    def _run_in_thread(self, msg: Dict[str, Any]):
        """Buat event loop baru di thread terpisah"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.process(msg))
        finally:
            loop.close()

    async def process(self, msg: Dict[str, Any]):
        doc_id = msg["document_id"]
        pdf_path = msg["pdf_path"]
        
        # Buat instance db baru per thread (tidak share connection)
        db = Database()
        
        try:
            print(f"🚀 Processing started: {doc_id}")
            await db.connect()
            await db.update_document_status(doc_id, "processing")

            from ..extractors.pdf_processor import PDFProcessor
            processor = PDFProcessor(pdf_path, doc_id)
            result = await processor.process()

            await db.save_document_outputs(
                doc_id,
                result["output_paths"]["markdown_path"],
                result["output_paths"]["json_path"],
                result["output_paths"]["images_folder"]
            )
            await db.update_document_status(doc_id, "completed")
            print(f"✅ Successfully completed: {doc_id}")

        except Exception as e:
            print(f"❌ Failed processing {doc_id}: {e}")
            try:
                await db.update_document_status(doc_id, "failed", str(e))
            except:
                pass
        finally:
            # Pastikan koneksi db ditutup
            try:
                await db.disconnect()
            except:
                pass