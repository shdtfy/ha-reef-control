#!/usr/bin/with-contenv bashio
set -e
bashio::log.info "Starting Reef Control TC420 USB bridge..."
exec python3 /app/tc420_service.py
