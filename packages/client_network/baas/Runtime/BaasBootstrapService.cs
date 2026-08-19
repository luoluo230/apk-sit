using System;
using System.Collections;
using UnityEngine;

namespace MAClient.Network.Baas
{
    /// <summary>One-call bootstrap + optional guest login for BaaS projects.</summary>
    public sealed class BaasBootstrapService : INetworkModule
    {
        public const string FrameworkIdValue = "casual_baas";

        readonly BaasNetworkSettings _settings;
        readonly BaasNetworkModule _module = new BaasNetworkModule();
        BaasClientContext _context;

        public string FrameworkId => FrameworkIdValue;
        public bool IsReady => _context != null && !string.IsNullOrEmpty(_context.ServiceId);
        public BaasClientContext Context => _context;
        public BaasNetworkModule Module => _module;

        public BaasBootstrapService(BaasNetworkSettings settings)
        {
            _settings = settings != null ? settings : BaasNetworkSettings.LoadOrDefault();
        }

        public IEnumerator BootstrapCoroutine(Action<bool, string> onComplete)
        {
            _context = null;
            BaasBootstrapResponse bootstrap = null;
            string bootstrapJson = null;
            string err = null;

            yield return _module.BootstrapCoroutine(
                _settings.PortalBaseUrl,
                _settings.GameId,
                _settings.GameKey,
                _settings.EnvKey,
                _settings.ApiKey,
                (resp, error) =>
                {
                    bootstrap = resp;
                    err = error;
                },
                raw => bootstrapJson = raw);

            if (!string.IsNullOrEmpty(err) || bootstrap == null || !bootstrap.ok)
            {
                onComplete?.Invoke(false, err ?? bootstrap?.error ?? "baas bootstrap failed");
                yield break;
            }

            _context = new BaasClientContext
            {
                PortalBaseUrl = _module.PortalBaseUrl,
                ServiceId = string.IsNullOrEmpty(_settings.ServiceIdOverride) ? _module.ServiceId : _settings.ServiceIdOverride,
                ApiKey = _module.ApiKey,
                PublicApiBase = _module.PublicApiBase,
            };
            if (!string.IsNullOrEmpty(bootstrapJson))
                _context.Endpoints.LoadFromBootstrapJson(bootstrapJson, _context.ServiceId);

            if (!_settings.AutoGuestLoginAfterBootstrap)
            {
                onComplete?.Invoke(true, null);
                yield break;
            }

            var auth = new BaasAuthClient(_context);
            BaasApiResponse<string> loginResp = null;
            yield return auth.GuestLoginAsync(_settings.GuestDisplayName, r => loginResp = r);
                if (loginResp == null || !loginResp.ok)
                {
                    onComplete?.Invoke(false, loginResp?.UserMessage ?? "guest login failed");
                    yield break;
                }
                var token = BaasApiResponse<string>.ExtractString(loginResp.data ?? string.Empty, "token");
                var pid = BaasApiResponse<string>.ExtractString(loginResp.data ?? string.Empty, "player_id");
                if (!string.IsNullOrEmpty(token) && !string.IsNullOrEmpty(pid))
                    _context.SetSession(token, pid);
                onComplete?.Invoke(true, null);
        }

        public static IEnumerator RunFromHotUpdateConfig(
            string portalBaseUrl,
            string gameId,
            string gameKey,
            string envKey,
            string apiKey,
            Action<BaasBootstrapService, bool, string> onComplete)
        {
            var settings = BaasNetworkSettings.LoadOrDefault();
            settings.PortalBaseUrl = portalBaseUrl ?? settings.PortalBaseUrl;
            settings.GameId = gameId ?? settings.GameId;
            settings.GameKey = gameKey ?? settings.GameKey;
            settings.EnvKey = envKey ?? settings.EnvKey;
            if (!string.IsNullOrEmpty(apiKey)) settings.ApiKey = apiKey;
            var svc = new BaasBootstrapService(settings);
            bool ok = false;
            string err = null;
            yield return svc.BootstrapCoroutine((success, error) => { ok = success; err = error; });
            onComplete?.Invoke(svc, ok, err);
        }
    }
}
