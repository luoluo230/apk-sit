namespace MAClient.Network.Baas
{
    /// <summary>
    /// BaaS 功能开关键名，与服务端 registry.FEATURE_CATALOG 保持一致。
    /// 新项目接入时只需在管理台勾选对应功能，客户端通过 bootstrap 的 feature_flags 感知。
    /// </summary>
    public static class BaasFeatureKeys
    {
        /// <summary>账号登录（游客/密码）。</summary>
        public const string Login = "login";
        /// <summary>游戏公告。</summary>
        public const string Announce = "announce";
        /// <summary>邮件系统。</summary>
        public const string Mail = "mail";
        /// <summary>云存档 KV。</summary>
        public const string CloudSave = "cloudsave";
        /// <summary>排行榜。</summary>
        public const string Leaderboard = "leaderboard";
        /// <summary>商城与经济（金币/商品）。</summary>
        public const string Economy = "economy";
        /// <summary>成就系统。</summary>
        public const string Achievement = "achievement";
        /// <summary>礼包码兑换。</summary>
        public const string Gift = "gift";
        /// <summary>公会。</summary>
        public const string Guild = "guild";
        /// <summary>战令。</summary>
        public const string BattlePass = "battlepass";
        /// <summary>周期任务（日/周）。</summary>
        public const string PeriodicTask = "periodic_task";
        /// <summary>防沉迷合规。</summary>
        public const string Compliance = "compliance";
        /// <summary>PVE 推图战斗（剑与远征式）。</summary>
        public const string Pve = "pve";
        /// <summary>异步竞技场 PVP。</summary>
        public const string Arena = "arena";
        /// <summary>实时房间 PVP（可选）。</summary>
        public const string Pvp = "pvp";
    }
}
