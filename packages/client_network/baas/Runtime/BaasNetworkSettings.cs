using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

namespace MAClient.Network.Baas
{
    /// <summary>各业务 Feature Client 的统一标记接口，便于扩展与测试替身。</summary>
    public interface IBaasFeatureClient
    {
        /// <summary>所属会话上下文。</summary>
        BaasClientContext Context { get; }
    }

    /// <summary>网络模块生命周期：Bootstrap 完成后 IsReady=true。</summary>
    public interface INetworkModule
    {
        string FrameworkId { get; }
        bool IsReady { get; }
        IEnumerator BootstrapCoroutine(Action<bool, string> onComplete);
    }

    /// <summary>
    /// BaaS 连接配置（可放在 Resources/Protocol/BaasNetworkSettings）。
    /// Portal 地址、项目凭证、是否自动游客登录等。
    /// </summary>
    [CreateAssetMenu(fileName = "BaasNetworkSettings", menuName = "MAClient/BaaS Network Settings")]
    public sealed class BaasNetworkSettings : ScriptableObject
    {
        [Header("Portal 门户")]
        public string PortalBaseUrl = "http://127.0.0.1:5004";
        public string EnvKey = "development";

        [Header("项目凭证（与 Portal 项目设置一致）")]
        public string GameId = "";
        public string GameKey = "";
        [Tooltip("服务 API 密钥，bootstrap 不会下发，需在 Inspector 或环境变量配置")]
        public string ApiKey = "";

        [Header("可选覆盖")]
        public string ServiceIdOverride = "";
        [Tooltip("Bootstrap 成功后是否自动游客登录")]
        public bool AutoGuestLoginAfterBootstrap = true;
        public string GuestDisplayName = "Player";

        public static BaasNetworkSettings LoadOrDefault()
        {
            var loaded = Resources.Load<BaasNetworkSettings>("Protocol/BaasNetworkSettings");
            return loaded != null ? loaded : CreateInstance<BaasNetworkSettings>();
        }
    }
}
