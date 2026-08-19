using System;
using System.IO;
using UnityEngine;

namespace MAClient.Network.Abstractions
{
    /// <summary>
    /// Base-project gate: detects imported client network modules without hard references.
    /// </summary>
    public static class ClientNetworkModuleGate
    {
        const string ManifestFileName = "client_network_modules.json";

        public static bool HasTopologyModule => IsModuleInstalled("topology");
        public static bool HasBaasModule => IsModuleInstalled("baas");

        public static bool IsModuleInstalled(string moduleKey)
        {
            var key = (moduleKey ?? string.Empty).Trim().ToLowerInvariant();
            if (string.IsNullOrEmpty(key)) return false;
            foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
            {
                var name = asm.GetName().Name ?? string.Empty;
                if (key == "topology" && name == "MAClient.Network.Topology") return true;
                if (key == "baas" && name == "MAClient.Network.Baas") return true;
            }
            var manifest = LoadManifest();
            if (manifest == null || manifest.modules == null) return false;
            foreach (var row in manifest.modules)
            {
                if (string.Equals(row.key, key, StringComparison.OrdinalIgnoreCase) && row.installed)
                    return true;
            }
            return false;
        }

        static ClientNetworkModulesManifest LoadManifest()
        {
            try
            {
                var path = Path.Combine(Application.streamingAssetsPath, ManifestFileName);
                if (!File.Exists(path)) return null;
                return JsonUtility.FromJson<ClientNetworkModulesManifest>(File.ReadAllText(path));
            }
            catch
            {
                return null;
            }
        }

        [Serializable]
        class ClientNetworkModulesManifest
        {
            public ModuleRow[] modules;
        }

        [Serializable]
        class ModuleRow
        {
            public string key;
            public bool installed;
        }
    }
}
