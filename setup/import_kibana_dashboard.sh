#!/bin/bash

# Script to import Kibana dashboard for MLflow monitoring
# This script should be run after Kibana is up and running

echo "Importing MLflow Dashboard to Kibana..."

# Wait for Kibana to be ready
echo "Waiting for Kibana to be ready..."
until curl -s http://localhost:5601/api/status; do
    echo "Kibana not ready yet, waiting..."
    sleep 5
done

# Import the dashboard
echo "Importing dashboard configuration..."
curl -X POST "http://localhost:5601/api/kibana/dashboards/import" \
  -H "kbn-xsrf: true" \
  -H "Content-Type: application/json" \
  -d @kibana/config/dashboard.json

echo "Dashboard import completed!"
echo "You can now access the MLflow Dashboard at: http://localhost:5601/app/kibana#/dashboard/mlflow-dashboard" 