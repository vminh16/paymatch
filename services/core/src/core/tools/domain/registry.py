"""Pure domain registry of all 30 v1 read-only tool definitions matching contracts/openapi/core-internal.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from paymatch_contracts import internal as internal_models

Provenance = Literal["trusted", "untrusted"]


@dataclass(frozen=True)
class ToolSpec:
    tool_id: str
    description: str
    default_provenance: Provenance
    input_model: type[Any]
    output_model: type[Any]
    scope: Literal["tenant"] = "tenant"

    def to_definition(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "description": self.description,
            "input_schema": self.input_model.model_json_schema(),
            "output_schema": self.output_model.model_json_schema(),
            "default_provenance": self.default_provenance,
            "scope": self.scope,
        }


V1_TOOL_SPECS: dict[str, ToolSpec] = {
    "invoices": ToolSpec(
        tool_id="invoices",
        description="Đọc hóa đơn chuẩn hóa (số trusted, chữ người bán trong untrusted).",
        default_provenance="untrusted",
        input_model=internal_models.InvoicesInput,
        output_model=internal_models.InvoicesOutput,
    ),
    "vendor_contracts": ToolSpec(
        tool_id="vendor_contracts",
        description="Đọc hợp đồng khung đang hiệu lực của nhà cung cấp.",
        default_provenance="trusted",
        input_model=internal_models.VendorContractsInput,
        output_model=internal_models.VendorContractsOutput,
    ),
    "price_check": ToolSpec(
        tool_id="price_check",
        description="Đối chiếu đơn giá trên hóa đơn với đơn giá và quy cách trong hợp đồng khung.",
        default_provenance="trusted",
        input_model=internal_models.PriceCheckInput,
        output_model=internal_models.PriceCheckOutput,
    ),
    "price_history": ToolSpec(
        tool_id="price_history",
        description="Tra cứu lịch sử đơn giá mua trước đây theo SKU.",
        default_provenance="trusted",
        input_model=internal_models.PriceHistoryInput,
        output_model=internal_models.PriceHistoryOutput,
    ),
    "purchase_orders": ToolSpec(
        tool_id="purchase_orders",
        description="Đọc đơn đặt hàng (PO) liên quan tới nhà cung cấp.",
        default_provenance="trusted",
        input_model=internal_models.PurchaseOrdersInput,
        output_model=internal_models.PurchaseOrdersOutput,
    ),
    "goods_receipts": ToolSpec(
        tool_id="goods_receipts",
        description="Đọc phiếu nhập kho đã được quản lý quán/bếp xác nhận.",
        default_provenance="trusted",
        input_model=internal_models.GoodsReceiptsInput,
        output_model=internal_models.GoodsReceiptsOutput,
    ),
    "payables_ledger": ToolSpec(
        tool_id="payables_ledger",
        description="Đọc sổ công nợ phải trả theo nhà cung cấp.",
        default_provenance="trusted",
        input_model=internal_models.PayablesLedgerInput,
        output_model=internal_models.PayablesLedgerOutput,
    ),
    "three_way_match": ToolSpec(
        tool_id="three_way_match",
        description="Chạy đối chiếu 3 chứng từ PO ↔ phiếu nhập ↔ hóa đơn bằng code.",
        default_provenance="trusted",
        input_model=internal_models.ThreeWayMatchInput,
        output_model=internal_models.ThreeWayMatchOutput,
    ),
    "inbox": ToolSpec(
        tool_id="inbox",
        description="Đọc email liên quan nhà cung cấp trong hộp thư nhận hóa đơn (untrusted).",
        default_provenance="untrusted",
        input_model=internal_models.InboxInput,
        output_model=internal_models.InboxOutput,
    ),
    "chat_messages": ToolSpec(
        tool_id="chat_messages",
        description="Đọc tin nhắn hội thoại Zalo với nhà cung cấp (untrusted).",
        default_provenance="untrusted",
        input_model=internal_models.ChatMessagesInput,
        output_model=internal_models.ChatMessagesOutput,
    ),
    "vendor_registry": ToolSpec(
        tool_id="vendor_registry",
        description="Tra cứu danh bạ NCC, tài khoản đã xác minh, SĐT lưu sẵn và lịch sử xác minh F12.",
        default_provenance="trusted",
        input_model=internal_models.VendorRegistryInput,
        output_model=internal_models.VendorRegistryOutput,
    ),
    "cross_alerts": ToolSpec(
        tool_id="cross_alerts",
        description="Kiểm tra chỉ báo của hóa đơn có khớp cảnh báo chéo trên mạng lưới MoMo hay không.",
        default_provenance="trusted",
        input_model=internal_models.CrossAlertsInput,
        output_model=internal_models.CrossAlertsOutput,
    ),
    "official_fraud_list": ToolSpec(
        tool_id="official_fraud_list",
        description="Tra cứu chỉ báo (TK, SĐT, MST) trong danh sách cảnh báo gian lận chính thức (SIMO).",
        default_provenance="trusted",
        input_model=internal_models.OfficialFraudListInput,
        output_model=internal_models.OfficialFraudListOutput,
    ),
    "einvoice_portal": ToolSpec(
        tool_id="einvoice_portal",
        description="Tra cứu hiệu lực hóa đơn trên cổng HĐĐT của cơ quan thuế.",
        default_provenance="trusted",
        input_model=internal_models.EinvoicePortalInput,
        output_model=internal_models.EinvoicePortalOutput,
    ),
    "tax_id_lookup": ToolSpec(
        tool_id="tax_id_lookup",
        description="Tra cứu trạng thái mã số thuế theo 10 mã Phụ lục I TT 90/2026/TT-BTC.",
        default_provenance="trusted",
        input_model=internal_models.TaxIdLookupInput,
        output_model=internal_models.TaxIdLookupOutput,
    ),
    "tax_risk_list": ToolSpec(
        tool_id="tax_risk_list",
        description="Kiểm tra MST có nằm trong danh sách doanh nghiệp rủi ro cao về thuế hay không.",
        default_provenance="trusted",
        input_model=internal_models.TaxRiskListInput,
        output_model=internal_models.TaxRiskListOutput,
    ),
    "utility_bills": ToolSpec(
        tool_id="utility_bills",
        description="Đọc lịch sử chỉ số và tiền điện/nước của quán.",
        default_provenance="trusted",
        input_model=internal_models.UtilityBillsInput,
        output_model=internal_models.UtilityBillsOutput,
    ),
    "utility_baseline": ToolSpec(
        tool_id="utility_baseline",
        description="Tính trung vị và khoảng bình thường 12 tháng điện/nước của quán.",
        default_provenance="trusted",
        input_model=internal_models.UtilityBaselineInput,
        output_model=internal_models.UtilityBaselineOutput,
    ),
    "momo_revenue": ToolSpec(
        tool_id="momo_revenue",
        description="Tra cứu doanh thu và số giao dịch MoMo theo quán trong tháng.",
        default_provenance="trusted",
        input_model=internal_models.MomoRevenueInput,
        output_model=internal_models.MomoRevenueOutput,
    ),
    "account_balance": ToolSpec(
        tool_id="account_balance",
        description="Đọc số dư hiện tại của ví MoMo Doanh Nghiệp.",
        default_provenance="trusted",
        input_model=internal_models.AccountBalanceInput,
        output_model=internal_models.AccountBalanceOutput,
    ),
    "spending_limits": ToolSpec(
        tool_id="spending_limits",
        description="Đọc mandate hiện hành, trần nền tảng và ngân sách tự chi còn lại trong ngày.",
        default_provenance="trusted",
        input_model=internal_models.SpendingLimitsInput,
        output_model=internal_models.SpendingLimitsOutput,
    ),
    "payment_policy_preview": ToolSpec(
        tool_id="payment_policy_preview",
        description="Chạy thử đánh giá Payment Gate (không tác dụng phụ) cho hóa đơn.",
        default_provenance="trusted",
        input_model=internal_models.PaymentPolicyPreviewInput,
        output_model=internal_models.PaymentPolicyPreviewOutput,
    ),
    "invoice_search": ToolSpec(
        tool_id="invoice_search",
        description="Tìm kiếm hóa đơn theo bộ lọc cấu trúc (chỉ phần số và tên NCC danh bạ).",
        default_provenance="trusted",
        input_model=internal_models.InvoiceSearchInput,
        output_model=internal_models.InvoiceSearchOutput,
    ),
    "invoice_explain": ToolSpec(
        tool_id="invoice_explain",
        description="Tra cứu trạng thái, màu và Finding đã lọc chữ của một hóa đơn.",
        default_provenance="trusted",
        input_model=internal_models.InvoiceExplainInput,
        output_model=internal_models.InvoiceExplainOutput,
    ),
    "spending_summary": ToolSpec(
        tool_id="spending_summary",
        description="Tổng hợp chi tiêu theo NCC, quán, loại hóa đơn hoặc tháng.",
        default_provenance="trusted",
        input_model=internal_models.SpendingSummaryInput,
        output_model=internal_models.SpendingSummaryOutput,
    ),
    "vendor_stats": ToolSpec(
        tool_id="vendor_stats",
        description="Thống kê số lượng hóa đơn, tổng tiền và cảnh báo theo nhà cung cấp.",
        default_provenance="trusted",
        input_model=internal_models.VendorStatsInput,
        output_model=internal_models.VendorStatsOutput,
    ),
    "price_trend": ToolSpec(
        tool_id="price_trend",
        description="Xu hướng đơn giá trung bình/min/max theo tháng so với giá hợp đồng.",
        default_provenance="trusted",
        input_model=internal_models.PriceTrendInput,
        output_model=internal_models.PriceTrendOutput,
    ),
    "queue_status": ToolSpec(
        tool_id="queue_status",
        description="Thống kê số hóa đơn theo trạng thái và tổng tiền đang chờ duyệt.",
        default_provenance="trusted",
        input_model=internal_models.QueueStatusInput,
        output_model=internal_models.QueueStatusOutput,
    ),
    "utility_summary": ToolSpec(
        tool_id="utility_summary",
        description="Tổng hợp chi phí điện nước các quán so với trung vị.",
        default_provenance="trusted",
        input_model=internal_models.UtilitySummaryInput,
        output_model=internal_models.UtilitySummaryOutput,
    ),
    "payment_history": ToolSpec(
        tool_id="payment_history",
        description="Tra cứu lịch sử thanh toán đã hoàn tất theo khoảng ngày.",
        default_provenance="trusted",
        input_model=internal_models.PaymentHistoryInput,
        output_model=internal_models.PaymentHistoryOutput,
    ),
}
