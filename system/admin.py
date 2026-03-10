from django.contrib import admin
from .models.accounts import Department, Workshop, Employee

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent')
    search_fields = ('name',)
    list_filter = ('parent',)

@admin.register(Workshop)
class WorkshopAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'description')
    search_fields = ('name', 'code')

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('get_full_name', 'employee_id', 'department', 'position', 'phone')
    search_fields = ('user__last_name', 'user__first_name', 'employee_id', 'phone')
    list_filter = ('department', 'workshops')
    # 使用 filter_horizontal 方便在后台多选管理的车间
    filter_horizontal = ('workshops',)

    def get_full_name(self, obj):
        return f"{obj.user.last_name}{obj.user.first_name}"
    get_full_name.short_description = "姓名"