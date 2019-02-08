from __future__ import absolute_import

import six

from collections import OrderedDict
from croniter import croniter
from django.core.exceptions import ValidationError
from rest_framework import serializers

from sentry.models import Project, MonitorStatus, MonitorType, ScheduleType


SCHEDULE_TYPES = OrderedDict([
    ('crontab', ScheduleType.CRONTAB),
    ('interval', ScheduleType.INTERVAL),
])

MONITOR_TYPES = OrderedDict([
    ('cron_job', MonitorType.CRON_JOB),
])

MONITOR_STATUSES = OrderedDict([
    ('active', MonitorStatus.ACTIVE),
    ('disabled', MonitorStatus.DISABLED),
])

INTERVAL_NAMES = ('year', 'month', 'week', 'day', 'hour', 'minute')

# XXX(dcramer): @reboot is not supported (as it cannot be)
NONSTANDARD_CRONTAB_SCHEDULES = {
    '@yearly': '0 0 1 1 *',
    '@annually': '0 0 1 1 *',
    '@monthly': '0 0 1 * *',
    '@weekly': '0 0 * * 0',
    '@daily': '0 0 * * *',
    '@hourly': '0 * * * *',
}


class CronJobValidator(serializers.Serializer):
    schedule_type = serializers.ChoiceField(
        choices=zip(SCHEDULE_TYPES.keys(), SCHEDULE_TYPES.keys()),
    )
    schedule = serializers.WritableField()

    def validate(self, attrs):
        if 'schedule_type' in attrs:
            schedule_type = SCHEDULE_TYPES[attrs['schedule_type']]
            attrs['schedule_type'] = schedule_type
        else:
            schedule_type = self.object['schedule_type']

        if 'schedule' in attrs:
            schedule = attrs['schedule']
            if schedule_type == ScheduleType.INTERVAL:
                if not isinstance(schedule, list):
                    raise ValidationError({
                        'schedule': ['Invalid value for schedule_type'],
                    })
                if not isinstance(schedule[0], int):
                    raise ValidationError({
                        'schedule': ['Invalid value for schedule frequency'],
                    })
                if schedule[1] not in INTERVAL_NAMES:
                    raise ValidationError({
                        'schedule': ['Invalid value for schedlue interval'],
                    })
            elif schedule_type == ScheduleType.CRONTAB:
                schedule = schedule.strip()
                if not isinstance(schedule, six.string_types):
                    raise ValidationError({
                        'schedule': ['Invalid value for schedule_type'],
                    })
                if schedule.startswith('@'):
                    try:
                        schedule = NONSTANDARD_CRONTAB_SCHEDULES[schedule]
                    except KeyError:
                        raise ValidationError({
                            'schedule': ['Schedule was not parseable'],
                        })
                if not croniter.is_valid(schedule):
                    raise ValidationError({
                        'schedule': ['Schedule was not parseable'],
                    })
                attrs['schedule'] = schedule
        return attrs


class MonitorValidator(serializers.Serializer):
    project = serializers.CharField()
    name = serializers.CharField()
    status = serializers.ChoiceField(
        choices=zip(MONITOR_STATUSES.keys(), MONITOR_STATUSES.keys()),
        default='active',
    )
    type = serializers.ChoiceField(
        choices=zip(MONITOR_TYPES.keys(), MONITOR_TYPES.keys())
    )

    def get_default_fields(self):
        type = self.init_data.get('type', self.object.get('type') if self.object else None)
        if type in MONITOR_TYPES:
            type = MONITOR_TYPES[type]
        if type == MonitorType.CRON_JOB:
            config = CronJobValidator()
        elif not type:
            return {}
        else:
            raise NotImplementedError
        return {'config': config}

    def validate(self, attrs):
        if 'type' in attrs:
            attrs['type'] = MONITOR_TYPES[attrs['type']]
        if 'status' in attrs:
            attrs['status'] = MONITOR_STATUSES[attrs['status']]
        if 'project' in attrs:
            try:
                attrs['project'] = Project.objects.get(
                    organization=self.context['organization'],
                    slug=attrs['project']
                )
            except Project.DoesNotExist:
                raise ValidationError({
                    'project': ['Invalid project']
                })
            if not self.context['access'].has_project_scope('project:write'):
                raise ValidationError({
                    'project': ['Insufficient access to project']
                })
        return attrs
