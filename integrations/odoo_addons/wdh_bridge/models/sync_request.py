"""Receipt and target creation commit in one Odoo transaction."""

import hashlib
import json
import math
import re

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from psycopg2 import IntegrityError


class SyncRequest(models.Model):
    _name = "wdh.sync.request"
    _description = "Approved WDH draft receipt"
    _key_unique = models.Constraint("UNIQUE(key)", "This request has already been processed.")

    key = fields.Char(required=True, readonly=True, index=True)
    request_hash = fields.Char(required=True, readonly=True)
    target_model = fields.Char(required=True, readonly=True)
    remote_id = fields.Integer(required=True, readonly=True)

    @api.model
    def apply_approved(self, key, target_model, values):
        if not self.env.user.has_group("wdh_bridge.group_wdh_bridge"):
            raise AccessError("WDH bridge permission required")
        if not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{64}", key):
            raise ValidationError("Invalid request key")
        allowed = {
            "res.partner": {"name"},
            "product.template": {"name", "default_code"},
            "crm.lead": {"name"},
            "purchase.order": {"partner_id", "currency_id", "order_line"},
            "sale.order": {"partner_id", "currency_id", "order_line"},
        }
        linking = (
            target_model in {"res.partner", "product.template"}
            and isinstance(values, dict)
            and set(values) == {"wdh_existing_id"}
            and type(values["wdh_existing_id"]) is int
            and values["wdh_existing_id"] > 0
        )
        if (
            target_model not in allowed
            or not isinstance(values, dict)
            or not values
            or (not linking and set(values) - allowed[target_model])
        ):
            raise ValidationError("Unsupported draft fields")
        if target_model not in self.env:
            raise ValidationError("Required business module is not installed")
        if target_model in {"purchase.order", "sale.order"}:
            if (
                type(values.get("partner_id")) is not int
                or values["partner_id"] <= 0
                or type(values.get("currency_id")) is not int
                or values["currency_id"] <= 0
            ):
                raise ValidationError("Partner and currency required")
            lines = values.get("order_line")
            if (
                not isinstance(lines, list)
                or len(lines) != 1
                or not isinstance(lines[0], list)
                or len(lines[0]) != 3
                or lines[0][:2] != [0, 0]
            ):
                raise ValidationError("Only one newly created draft line is supported")
            line = lines[0][2]
            quantity = "product_qty" if target_model == "purchase.order" else "product_uom_qty"
            if not isinstance(line, dict) or set(line) != {
                "product_id",
                "name",
                quantity,
                "price_unit",
                "product_uom_id",
            }:
                raise ValidationError("Unsupported order line")
            for field in (quantity, "price_unit"):
                if (
                    type(line[field]) not in {float, int}
                    or not math.isfinite(line[field])
                    or line[field] <= 0
                ):
                    raise ValidationError("Positive finite quantity and price required")
            for field in ("product_id", "product_uom_id"):
                if type(line[field]) is not int or line[field] <= 0:
                    raise ValidationError("Product and unit required")
            if not isinstance(line["name"], str) or not line["name"].strip():
                raise ValidationError("Line description required")
        elif not linking and (
            not isinstance(values.get("name"), str) or not values["name"].strip()
        ):
            raise ValidationError("Name required")
        request_hash = hashlib.sha256(
            json.dumps(
                [target_model, values], sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest()
        receipt = self.search([("key", "=", key)], limit=1)
        if receipt:
            if receipt.request_hash != request_hash:
                raise ValidationError("Request key reused with different data")
            return {"model": receipt.target_model, "remote_id": receipt.remote_id}
        try:
            with self.env.cr.savepoint():
                receipt = super().create(
                    {
                        "key": key,
                        "request_hash": request_hash,
                        "target_model": target_model,
                        "remote_id": 0,
                    }
                )
                if linking:
                    record = self.env[target_model].browse(values["wdh_existing_id"]).exists()
                    if not record:
                        raise ValidationError("Selected record no longer exists")
                    record.read(["id", "name"])
                else:
                    record = (
                        self.env[target_model]
                        .with_context(mail_create_nosubscribe=True, tracking_disable=True)
                        .create(values)
                    )
                if target_model in {"purchase.order", "sale.order"} and record.state != "draft":
                    raise ValidationError("Only draft documents are supported")
                super(SyncRequest, receipt).write({"remote_id": record.id})
                return {"model": target_model, "remote_id": record.id}
        except IntegrityError:
            receipt = self.search([("key", "=", key)], limit=1)
            if not receipt or receipt.request_hash != request_hash:
                raise ValidationError("Concurrent request; retry the same key") from None
            return {"model": receipt.target_model, "remote_id": receipt.remote_id}

    @api.model_create_multi
    def create(self, values_list):
        raise AccessError("Use apply_approved")

    def write(self, values):
        raise AccessError("Receipts are immutable")

    def unlink(self):
        raise AccessError("Receipts are immutable")
