using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;

namespace MAClient.Network.Baas.PlayModeTests
{
    public class BaasRoomFanoutPlayModeTests
    {
        [UnityTest]
        public IEnumerator Bootstrap_and_guest_login_returns_error_code_envelope()
        {
            var portal = System.Environment.GetEnvironmentVariable("BAAS_E2E_PORTAL") ?? "http://127.0.0.1:5004";
            var gameId = System.Environment.GetEnvironmentVariable("BAAS_E2E_GAME_ID") ?? "baas-production-e2e";
            var gameKey = System.Environment.GetEnvironmentVariable("BAAS_E2E_GAME_KEY") ?? "baas-production-e2e-key";
            var apiKey = System.Environment.GetEnvironmentVariable("BAAS_E2E_API_KEY") ?? string.Empty;
            if (string.IsNullOrEmpty(apiKey))
            {
                Assert.Ignore("BAAS_E2E_API_KEY not set");
                yield break;
            }
            var settings = ScriptableObject.CreateInstance<BaasNetworkSettings>();
            settings.PortalBaseUrl = portal;
            settings.GameId = gameId;
            settings.GameKey = gameKey;
            settings.ApiKey = apiKey;
            settings.AutoGuestLoginAfterBootstrap = true;
            var svc = new BaasBootstrapService(settings);
            bool ok = false;
            string err = null;
            yield return svc.BootstrapCoroutine((success, error) => { ok = success; err = error; });
            Assert.IsTrue(ok, err ?? "bootstrap failed");
            Assert.IsNotNull(svc.Context);
            Assert.IsFalse(string.IsNullOrEmpty(svc.Context.PlayerId));
        }
    }
}
