using System.Collections;

namespace MAClient.Network.Baas
{
    /// <summary>应用内购：商品列表、下单、验单发货。</summary>
    public sealed class BaasIapClient : IBaasFeatureClient
    {
        readonly BaasClientContext _ctx;
        public BaasClientContext Context => _ctx;
        public BaasIapClient(BaasClientContext ctx) { _ctx = ctx ?? throw new System.ArgumentNullException(nameof(ctx)); }

        public IEnumerator ListProductsAsync(Action<BaasApiResponse<string>> onComplete)
        {
            yield return BaasHttp.Get(_ctx.ApiPrefix + "/iap/products", _ctx.PlayerHeaders(), onComplete);
        }

        public IEnumerator CreateOrderAsync(string productId, string platform, Action<BaasApiResponse<string>> onComplete)
        {
            var body = "{\"product_id\":\"" + BaasJsonBody.Escape(productId) + "\",\"platform\":\"" + BaasJsonBody.Escape(platform ?? "dev") + "\"}";
            yield return BaasHttp.PostJson(_ctx.ApiPrefix + "/iap/orders", body, _ctx.PlayerHeaders(), onComplete);
        }

        public IEnumerator VerifyOrderAsync(string orderId, string receipt, string platform, Action<BaasApiResponse<string>> onComplete)
        {
            var body = "{\"receipt\":\"" + BaasJsonBody.Escape(receipt ?? "") + "\",\"platform\":\"" + BaasJsonBody.Escape(platform ?? "dev") + "\"}";
            yield return BaasHttp.PostJson(_ctx.ApiPrefix + "/iap/orders/" + Uri.EscapeDataString(orderId) + "/verify", body, _ctx.PlayerHeaders(), onComplete);
        }
    }
}
