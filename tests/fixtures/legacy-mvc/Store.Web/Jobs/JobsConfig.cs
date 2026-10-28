public static class JobsConfig
{
    public static void Register()
    {
        RecurringJob.AddOrUpdate("expire-carts", () => new CartJobs().ExpireCarts(), Cron.Hourly());
    }
}
