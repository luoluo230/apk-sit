using System;
using System.Collections;
using System.Reflection;
using UnityEngine;

namespace MAClient.Network.Abstractions
{
    /// <summary>Reflection bridge so shell Main.cs can bootstrap BaaS without hard reference.</summary>
    public static class BaasBootstrapBridge
    {
        public static bool TryRunBootstrap(
            string portalBaseUrl,
            string gameId,
            string gameKey,
            string envKey,
            string apiKey,
            MonoBehaviour host,
            Action<bool, string> onComplete)
        {
            if (!ClientNetworkModuleGate.HasBaasModule)
            {
                onComplete?.Invoke(false, "BaaS module not installed");
                return false;
            }
            if (host == null)
            {
                onComplete?.Invoke(false, "host required");
                return false;
            }
            host.StartCoroutine(RunCoroutine(portalBaseUrl, gameId, gameKey, envKey, apiKey, onComplete));
            return true;
        }

        static IEnumerator RunCoroutine(
            string portalBaseUrl,
            string gameId,
            string gameKey,
            string envKey,
            string apiKey,
            Action<bool, string> onComplete)
        {
            var baasAsm = FindAssembly("MAClient.Network.Baas");
            if (baasAsm == null)
            {
                onComplete?.Invoke(false, "MAClient.Network.Baas assembly missing");
                yield break;
            }
            var svcType = baasAsm.GetType("MAClient.Network.Baas.BaasBootstrapService");
            var settingsType = baasAsm.GetType("MAClient.Network.Baas.BaasNetworkSettings");
            if (svcType == null || settingsType == null)
            {
                onComplete?.Invoke(false, "BaasBootstrapService types missing");
                yield break;
            }
            var settings = ScriptableObject.CreateInstance(settingsType);
            settingsType.GetField("PortalBaseUrl")?.SetValue(settings, portalBaseUrl ?? string.Empty);
            settingsType.GetField("GameId")?.SetValue(settings, gameId ?? string.Empty);
            settingsType.GetField("GameKey")?.SetValue(settings, gameKey ?? string.Empty);
            settingsType.GetField("EnvKey")?.SetValue(settings, envKey ?? "development");
            settingsType.GetField("ApiKey")?.SetValue(settings, apiKey ?? string.Empty);
            var svc = Activator.CreateInstance(svcType, settings);
            var method = svcType.GetMethod("BootstrapCoroutine");
            if (method == null)
            {
                onComplete?.Invoke(false, "BootstrapCoroutine missing");
                yield break;
            }
            bool done = false;
            bool ok = false;
            string err = null;
            var enumerator = method.Invoke(svc, new object[]
            {
                (Action<bool, string>)((success, error) => { ok = success; err = error; done = true; })
            }) as IEnumerator;
            if (enumerator == null)
            {
                onComplete?.Invoke(false, "BootstrapCoroutine returned null");
                yield break;
            }
            while (!done && enumerator.MoveNext()) yield return enumerator.Current;
            onComplete?.Invoke(ok, err);
        }

        static Assembly FindAssembly(string name)
        {
            foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
            {
                if (asm.GetName().Name == name) return asm;
            }
            return null;
        }
    }
}
