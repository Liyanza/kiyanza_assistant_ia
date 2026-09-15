from radio_capture import capture_stream

result = capture_stream(
    "https://broadcasting-channels.com:9043/listen.mp3",
    duration_seconds=15,
    output_path="captures/test_balafon.wav"
)
print(result)
