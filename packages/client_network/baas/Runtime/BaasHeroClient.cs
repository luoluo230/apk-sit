using System;
using System.Collections;

namespace MAClient.Network.Baas
{
    /// <summary>英雄养成：背包、升级、装备。</summary>
    public sealed class BaasHeroClient : IBaasFeatureClient
    {
        readonly BaasClientContext _ctx;
        public BaasClientContext Context => _ctx;
        public BaasHeroClient(BaasClientContext ctx) { _ctx = ctx ?? throw new ArgumentNullException(nameof(ctx)); }

        public IEnumerator GetRosterAsync(Action<BaasApiResponse<string>> onComplete)
        {
            yield return BaasHttp.Get(_ctx.ApiPrefix + "/heroes/roster", _ctx.PlayerHeaders(), onComplete);
        }

        public IEnumerator LevelUpAsync(int heroId, Action<BaasApiResponse<string>> onComplete)
        {
            yield return BaasHttp.PostJson(_ctx.ApiPrefix + "/heroes/" + heroId + "/level-up", "{}", _ctx.PlayerHeaders(), onComplete);
        }

        public IEnumerator EquipAsync(int heroId, string slot, string equipmentId, Action<BaasApiResponse<string>> onComplete)
        {
            var body = "{\"slot\":\"" + BaasJsonBody.Escape(slot) + "\",\"equipment_id\":\"" + BaasJsonBody.Escape(equipmentId ?? "") + "\"}";
            yield return BaasHttp.PostJson(_ctx.ApiPrefix + "/heroes/" + heroId + "/equip", body, _ctx.PlayerHeaders(), onComplete);
        }
    }
}
