// apk-site 注入：管理内实例固定管理员，始终覆盖以便 API 可用
import jenkins.model.*
import hudson.security.*

def j = Jenkins.getInstance()
def realm = new HudsonPrivateSecurityRealm(false)
realm.createAccount("admin", "admin123")
j.setSecurityRealm(realm)
j.setAuthorizationStrategy(new hudson.security.FullControlOnceLoggedInAuthorizationStrategy())
j.save()
