from calendar import day_name

from django import template

register = template.Library()


@register.filter
def weekday_name(value):
    return day_name[value]
