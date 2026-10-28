namespace Orders.Api.Endpoints;

public static class OrdersEndpoints
{
    public static void Map(WebApplication app)
    {
        app.MapGet("/orders/{id}", (Guid id) => Results.Ok());
        app.MapPost("/orders", () => Results.Created());
        var debug = Environment.GetEnvironmentVariable("ORDERS_DEBUG");
    }
}
