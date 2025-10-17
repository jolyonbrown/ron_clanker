"""
Celery application configuration for Ron Clanker's FPL system.

Configures Celery with Redis as the message broker and result backend.
Sets up Celery Beat for scheduled autonomous operations.
"""

import os
from celery import Celery
from celery.schedules import crontab

# Redis connection from environment or default
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# Create Celery app
app = Celery(
    'ron_clanker',
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=['tasks.scheduled_tasks']
)

# Celery configuration
app.conf.update(
    # Timezone
    timezone='Europe/London',
    enable_utc=True,

    # Task settings
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    task_track_started=True,
    task_time_limit=600,  # 10 minutes max per task
    task_soft_time_limit=540,  # 9 minute soft limit

    # Worker settings
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,

    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour
    result_backend_transport_options={
        'master_name': 'mymaster'
    },

    # Beat schedule - Ron's autonomous operation schedule
    beat_schedule={
        # Daily data refresh at 6:00 AM
        'daily-data-refresh': {
            'task': 'tasks.scheduled_tasks.daily_data_refresh',
            'schedule': crontab(hour=6, minute=0),
            'options': {
                'expires': 3600,
            }
        },

        # Check for gameweek deadlines every 6 hours
        'gameweek-deadline-monitor': {
            'task': 'tasks.scheduled_tasks.check_gameweek_deadlines',
            'schedule': crontab(minute=0, hour='*/6'),
            'options': {
                'expires': 3600,
            }
        },

        # Price change monitoring at 2:00 AM (before FPL price updates at 2:30 AM)
        'pre-price-change-check': {
            'task': 'tasks.scheduled_tasks.pre_price_change_analysis',
            'schedule': crontab(hour=2, minute=0),
            'options': {
                'expires': 1800,
            }
        },

        # Post-price change analysis at 3:00 AM (after updates)
        'post-price-change-check': {
            'task': 'tasks.scheduled_tasks.post_price_change_analysis',
            'schedule': crontab(hour=3, minute=0),
            'options': {
                'expires': 1800,
            }
        },

        # Weekly review on Mondays at 10:00 AM (after gameweek completes)
        'weekly-gameweek-review': {
            'task': 'tasks.scheduled_tasks.post_gameweek_review',
            'schedule': crontab(hour=10, minute=0, day_of_week=1),
            'options': {
                'expires': 7200,
            }
        },
    },
)

if __name__ == '__main__':
    app.start()
