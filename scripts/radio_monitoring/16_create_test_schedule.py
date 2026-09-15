import sys
sys.path.insert(0, "scripts/radio_monitoring")
from datetime import datetime, timedelta
from radio_schedule import create_monitoring_entry

schedule_id = create_monitoring_entry(
    station_name="Balafon",
    stream_url="https://broadcasting-channels.com:9043/listen.mp3",
    reference_spot_path="test_audio/spot_reference.wav",
    planned_datetime=datetime.utcnow() + timedelta(minutes=2),
    capture_lead_minutes=1,
    capture_duration_seconds=300,
)
print("Cree :", schedule_id)
