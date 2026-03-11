from django.urls import path
from django.contrib.auth.views import LoginView
from django_ratelimit.decorators import ratelimit

# 注意：这里故意不写 app_name = 'system'
# 因为我们要复用 Django 默认的 url name 'login'，以兼容代码里的 LOGIN_REDIRECT_URL 等配置

# 定义登录防爆破限流器：针对 IP 进行限制，5分钟内最多尝试5次，仅限制 POST（真正提交账号密码时）
login_limit = ratelimit(key='ip', rate='5/5m', method='POST', block=True)

urlpatterns = [
    # 覆盖 django 默认的 login 路由，并挂载限流器
    path('login/', login_limit(LoginView.as_view(template_name='registration/login.html')), name='login'),
]