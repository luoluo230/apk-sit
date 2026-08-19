using System;
using System.Collections;

namespace MAClient.Network.Baas
{
    /// <summary>
    /// BaaS 功能客户端统一入口。登录/bootstrap 完成后，通过本类一次性获取各模块客户端。
    /// </summary>
    public sealed class BaasFeatureHub
    {
        readonly BaasClientContext _ctx;

        public BaasFeatureHub(BaasClientContext ctx)
        {
            _ctx = ctx ?? throw new ArgumentNullException(nameof(ctx));
        }

        /// <summary>账号：游客/密码登录。</summary>
        public BaasAuthClient Auth => new BaasAuthClient(_ctx);
        /// <summary>公告：拉取有效公告列表。</summary>
        public BaasAnnounceClient Announce => new BaasAnnounceClient(_ctx);
        /// <summary>邮件：收件箱与领取。</summary>
        public BaasMailClient Mail => new BaasMailClient(_ctx);
        /// <summary>云存档：KV 读写。</summary>
        public BaasCloudSaveClient CloudSave => new BaasCloudSaveClient(_ctx);
        /// <summary>排行榜：提交分数与查询榜单。</summary>
        public BaasLeaderboardClient Leaderboard => new BaasLeaderboardClient(_ctx);
        /// <summary>商城/钱包：商品列表、购买、余额。</summary>
        public BaasShopClient Shop => new BaasShopClient(_ctx);
        /// <summary>成就：列表、进度上报、领取。</summary>
        public BaasAchievementClient Achievement => new BaasAchievementClient(_ctx);
        /// <summary>礼包码：兑换。</summary>
        public BaasGiftClient Gift => new BaasGiftClient(_ctx);
        /// <summary>公会：创建、查询、加入。</summary>
        public BaasGuildClient Guild => new BaasGuildClient(_ctx);
        /// <summary>战令：状态、经验、领取。</summary>
        public BaasBattlePassClient BattlePass => new BaasBattlePassClient(_ctx);
        /// <summary>周期任务：列表、进度、领取。</summary>
        public BaasTaskClient Task => new BaasTaskClient(_ctx);
        /// <summary>防沉迷：会话、心跳、实名。</summary>
        public BaasComplianceClient Compliance => new BaasComplianceClient(_ctx);
        /// <summary>PVE 推图：开战、结算、进度、体力。</summary>
        public BaasPveClient Pve => new BaasPveClient(_ctx);
        /// <summary>异步竞技场：对手列表、防守阵容、离线对战。</summary>
        public BaasArenaClient Arena => new BaasArenaClient(_ctx);
        /// <summary>实时房间 PVP（可选，AFK 类游戏通常不用）。</summary>
        public BaasRoomClient Room => new BaasRoomClient(_ctx);

        public BaasClientContext Context => _ctx;
    }
}
