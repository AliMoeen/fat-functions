public class Order {
    public double shipping(String country, double weight) {
        switch (country) {
            case "CA": return weight > 5 ? 20 : 10;
            case "US": return 15;
            default:
                if (weight > 10) { return 50; }
                return 30;
        }
    }
}
