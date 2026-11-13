from django.contrib import admin

from .models import Activity, Membership, Notification, Project, Task, TaskComment


admin.site.register(Activity)
admin.site.register(Project)
admin.site.register(Membership)
admin.site.register(Task)
admin.site.register(TaskComment)
admin.site.register(Notification)
