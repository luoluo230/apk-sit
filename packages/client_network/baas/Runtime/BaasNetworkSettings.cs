using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

namespace MAClient.Network.Baas
{
    public interface IBaasFeatureClient
    {
        BaasClientContext Context { get; }
    }

    public interface INetworkModule
    {
        string FrameworkId { get; }
        bool IsReady { get; }
        IEnumerator BootstrapCoroutine(Action<bool, string> onComplete);
    }

    [CreateAssetMenu(fileName = "BaasNetworkSettings", menuName = "MAClient/BaaS Network Settings")]
    public sealed class BaasNetworkSettings : ScriptableObject
    {
        [Header("Portal")]
        public string PortalBaseUrl = "http://127.0.0.1:5004";
        public string EnvKey = "development";

        [Header("Project credentials")]
        public string GameId = "";
        public string GameKey = "";
        [Tooltip("Service API secret — never returned by bootstrap.")]
        public string ApiKey = "";

        [Header("Optional overrides")]
        public string ServiceIdOverride = "";
        public bool AutoGuestLoginAfterBootstrap = true;
        public string GuestDisplayName = "Player";

        public static BaasNetworkSettings LoadOrDefault()
        {
            var loaded = Resources.Load<BaasNetworkSettings>("Protocol/BaasNetworkSettings");
            return loaded != null ? loaded : CreateInstance<BaasNetworkSettings>();
        }
    }
}
