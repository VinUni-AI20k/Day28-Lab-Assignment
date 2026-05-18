"""Register a scheduled deployment for kafka_to_delta_flow.

Usage (from host, with stack up):
    PREFECT_API_URL=http://localhost:4200/api python prefect/flows/deploy_scheduled.py

Creates a deployment visible in Prefect UI → Deployments page, scheduled every
5 minutes via the cron-style schedule, attached to the 'default-process' pool.
Non-blocking: prints summary and exits.
"""
from prefect.deployments import Deployment
from prefect.client.schemas.schedules import CronSchedule

from kafka_to_delta import kafka_to_delta_flow

if __name__ == "__main__":
    deployment = Deployment.build_from_flow(
        flow=kafka_to_delta_flow,
        name="kafka-to-delta-scheduled",
        work_pool_name="default-process",
        schedule=CronSchedule(cron="*/5 * * * *"),
        tags=["lab28", "data-pipeline"],
        description="Consume Kafka data.raw and persist to Delta Lake every 5 minutes.",
    )
    deployment_id = deployment.apply()
    print(f"[OK] Deployment created: id={deployment_id}")
    print(f"     View at: http://localhost:4200/deployments/deployment/{deployment_id}")
