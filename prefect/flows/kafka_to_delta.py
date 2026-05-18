import json
import os
from datetime import datetime

import pandas as pd
from kafka import KafkaConsumer
from prefect import flow, task

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")
DELTA_PATH = os.environ.get("DELTA_PATH", "./delta-lake/raw")


@task
def consume_from_kafka():
    consumer = KafkaConsumer(
        "data.raw",
        bootstrap_servers=KAFKA_BOOTSTRAP,
        auto_offset_reset="earliest",
        consumer_timeout_ms=5000,
        value_deserializer=lambda m: json.loads(m.decode()),
    )
    records = [msg.value for msg in consumer]
    print(f"Consumed {len(records)} records from Kafka")
    return records


@task
def save_to_delta(records):
    if not records:
        print("No records to save")
        return 0
    df = pd.DataFrame(records)
    os.makedirs(DELTA_PATH, exist_ok=True)
    fname = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.parquet"
    df.to_parquet(f"{DELTA_PATH}/{fname}")
    print(f"Saved {len(df)} records to {DELTA_PATH}/{fname}")
    return len(df)


@flow(name="kafka-to-delta")
def kafka_to_delta_flow():
    records = consume_from_kafka()
    return save_to_delta(records)


if __name__ == "__main__":
    kafka_to_delta_flow()
