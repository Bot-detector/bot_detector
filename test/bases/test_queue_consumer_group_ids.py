from pathlib import Path
import re

GROUP_ID_PATTERN = re.compile(r'KafkaConsumerConfig\(group_id="([^"]+)"\)')

EXPECTED_GROUP_IDS = {
    "bases/bot_detector/hiscore_scraper/core.py": ["scraper"],
    "bases/bot_detector/runemetrics_scraper/core.py": ["runemetrics_scraper"],
    "bases/bot_detector/worker_hiscore/core.py": ["highscore_worker"],
    "bases/bot_detector/worker_ml/core.py": ["ml_worker", "ml_worker"],
    "bases/bot_detector/worker_report/main.py": ["report_worker"],
    "bases/bot_detector/scrape_task_producer/core.py": ["scraper"],
}


def test_consumer_group_ids_match_expected_queue_wiring() -> None:
    for file_path, expected in EXPECTED_GROUP_IDS.items():
        contents = Path(file_path).read_text()
        found = GROUP_ID_PATTERN.findall(contents)
        assert found == expected, f"{file_path}: expected {expected}, got {found}"
