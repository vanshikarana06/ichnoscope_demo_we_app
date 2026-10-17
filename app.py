"""Main Flask application factory for storefront service."""

import sentry_sdk
from flask import Flask, jsonify, render_template

from observability import init_observability

# Initialize the Ichnoscope SDK at backend server startup before any route handlers are loaded
init_observability()

from routes.cart import cart_bp
from routes.checkout import checkout_bp
from routes.discounts import discounts_bp
from routes.inventory import inventory_bp
from routes.shipping import shipping_bp


def create_app() -> Flask:
    """Instantiate and configure Flask shop service."""
    init_observability()

    app = Flask(__name__)
    app.config["TESTING"] = False

    # Automatically capture 500 errors across all routes
    @app.errorhandler(500)
    def handle_500_error(error):
        """Capture 500 internal server errors across all routes."""
        orig_exc = getattr(error, "original_exception", None)
        if not orig_exc:
            sentry_sdk.capture_exception(error)
        msg = str(orig_exc) if orig_exc else str(error)
        return jsonify({
            "error": "Internal Server Error",
            "message": msg,
        }), 500

    # Register service blueprints
    app.register_blueprint(checkout_bp)
    app.register_blueprint(cart_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(shipping_bp)
    app.register_blueprint(discounts_bp)

    @app.get("/")
    def index_page():
        """Interactive storefront diagnostics dashboard."""
        return render_template("index.html")

    @app.get("/healthz")
    def health_check():
        """Service health check endpoint returning JSON status."""
        return jsonify({"status": "healthy", "service": "storefront-api"}), 200

    @app.route("/api/debug/test-error", methods=["GET", "POST"])
    def debug_test_error():
        """Intentional test exception endpoint to verify Ichnoscope telemetry pipeline."""
        raise RuntimeError("Intentional test exception for Ichnoscope telemetry verification.")

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(host="0.0.0.0", port=5000)

