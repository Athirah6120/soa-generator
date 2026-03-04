import io
import zipfile
from datetime import date

import pandas as pd
import streamlit as st

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.lib.styles import getSampleStyleSheet


st.title("SOA Mass Generator - Australia")

# ===== Defaults =====
statement_as_at = st.date_input("Statement as at", value=date(2026, 1, 30))
subsidiary = "ShopBack Australia Pty Ltd"

uploaded = st.file_uploader("Upload CSV", type=["csv"])

if uploaded:
    df = pd.read_csv(uploaded)
    st.subheader("Preview")
    st.dataframe(df.head())

    # ===== Column Mapping =====
    merchant_col = st.selectbox("Merchant Column", df.columns)
    date_col = st.selectbox("Date Column", df.columns)
    doc_col = st.selectbox("Document No. Column", df.columns)

    # Keep selector but clarify meaning
    external_doc_col = st.selectbox("External Doc No. Column", df.columns)

    original_col = st.selectbox("Original Amount Column", df.columns)
    payment_col = st.selectbox("Payment Amount Column", df.columns)

    if st.button("Generate ZIP"):
        zip_buffer = io.BytesIO()

        styles = getSampleStyleSheet()
        style_cell = styles["Normal"]
        style_cell.fontName = "Helvetica"
        style_cell.fontSize = 8
        style_cell.leading = 9

        # ---------- Helpers ----------
        def to_num(s):
            return pd.to_numeric(s, errors="coerce").fillna(0.0)

        def fmt_money(val):
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return ""
            try:
                return f"{float(val):,.2f}"
            except:
                return str(val)

        def fmt_text(val):
            if pd.isna(val) or val is None:
                return ""
            return str(val)

        def p(txt):
            return Paragraph(txt.replace("\n", "<br/>"), style_cell)

        def compute_balances(m_df: pd.DataFrame) -> pd.DataFrame:
            """
            Document Amount = Original Amount - Payment Amount
            Accumulated Balance = running sum of Document Amount
            """
            m_df = m_df.copy()
            m_df["_original"] = to_num(m_df[original_col])
            m_df["_payment"] = to_num(m_df[payment_col])
            m_df["_document_amt"] = m_df["_original"] - m_df["_payment"]

            try:
                m_df["_date_sort"] = pd.to_datetime(m_df[date_col], errors="coerce")
                if m_df["_date_sort"].notna().any():
                    m_df = m_df.sort_values("_date_sort")
            except:
                pass

            m_df["_accumulated"] = m_df["_document_amt"].cumsum()
            return m_df

        def make_main_table(table_data, col_widths, font_size=8, pad_top=2, pad_bottom=2):
            t = Table(table_data, repeatRows=1, colWidths=col_widths)
            t.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), font_size),
                ("ALIGN", (0, 0), (2, 0), "LEFT"),
                ("ALIGN", (3, 0), (-1, 0), "CENTER"),
                ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.7, colors.black),
                ("TOPPADDING", (0, 0), (-1, 0), 4),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 4),

                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), font_size),
                ("VALIGN", (0, 1), (-1, -1), "TOP"),
                ("ALIGN", (0, 1), (2, -1), "LEFT"),
                ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
                ("TOPPADDING", (0, 1), (-1, -1), pad_top),
                ("BOTTOMPADDING", (0, 1), (-1, -1), pad_bottom),

                ("LINEABOVE", (0, 1), (-1, -1), 0, colors.white),
                ("LINEBELOW", (0, 1), (-1, -1), 0, colors.white),
                ("LINEBEFORE", (0, 0), (-1, -1), 0, colors.white),
                ("LINEAFTER", (0, 0), (-1, -1), 0, colors.white),
            ]))
            return t

        def draw_header(c, merchant, left, width, height):
            # Logo
            logo_path = "shopback_logo.png"
            try:
                logo = ImageReader(logo_path)
                iw, ih = logo.getSize()
                logo_h = 14 * mm
                logo_w = logo_h * (iw / ih)
                c.drawImage(
                    logo,
                    left,
                    height - 30 * mm,
                    width=logo_w,
                    height=logo_h,
                    mask="auto",
                )
            except:
                pass

            # Title
            c.setFont("Helvetica-Bold", 16)
            c.drawCentredString(width / 2, height - 40 * mm, "STATEMENT OF ACCOUNT")

            # To:
            c.setFont("Helvetica", 11)
            c.drawString(left, height - 60 * mm, "To:")
            c.drawString(left, height - 70 * mm, fmt_text(merchant))

            # Right header info
            c.setFont("Helvetica", 11)
            label_x = left + 90 * mm
            value_x = label_x + 40 * mm
            row1_y = height - 60 * mm
            row2_y = height - 70 * mm

            c.drawString(label_x, row1_y, "Statement as at")
            c.drawString(value_x, row1_y, statement_as_at.strftime("%d-%b-%Y"))

            c.drawString(label_x, row2_y, "Subsidiary")
            c.drawString(value_x, row2_y, subsidiary)

            # return y where table should start (top y)
            return height - 90 * mm

        def draw_totals_and_payment(c, left, table_x, col_widths, total_y_start, net_due):
            # TOTAL
            total_table = Table(
                [["TOTAL (AUD)", fmt_money(net_due)]],
                colWidths=[sum(col_widths[:-1]), col_widths[-1]],
            )
            total_table.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (0, 0), (0, 0), "RIGHT"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LINEABOVE", (0, 0), (-1, 0), 0.7, colors.black),
                ("LINEBELOW", (0, 0), (-1, 0), 0.7, colors.black),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            _, total_h = total_table.wrap(0, 0)
            total_y = total_y_start - 10 * mm - total_h
            total_table.drawOn(c, table_x, total_y)

            # NET DUE
            net_table = Table(
                [["NET AMOUNTS DUE FROM YOU", "(AUD)", fmt_money(net_due)]],
                colWidths=[sum(col_widths[:-2]), col_widths[-2], col_widths[-1]],
            )
            net_table.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (0, 0), (0, 0), "RIGHT"),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                ("LINEABOVE", (0, 0), (-1, 0), 0.7, colors.black),
                ("LINEBELOW", (0, 0), (-1, 0), 0.7, colors.black),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            _, net_h = net_table.wrap(0, 0)
            net_y = total_y - 10 * mm - net_h
            net_table.drawOn(c, table_x, net_y)

            # PAYMENT DETAILS
            pay_start_y = net_y - 55 * mm
            c.setFont("Helvetica", 10)
            c.drawString(left, pay_start_y, "Payment should be made to the following details:")

            label_x2 = left
            colon_x = left + 42 * mm
            value_x2 = left + 46 * mm

            pay_y = pay_start_y - 12 * mm
            payment_rows = [
                ("Bank Name", "ANZ Banking Group Limited"),
                ("Account Name", "ShopBack Australia Pty Ltd"),
                ("Account Number", "012010 307004743"),
                ("SWIFT Code", "ANZBAU3M"),
                ("Branch Code", ""),
                ("Currency", "AUD"),
            ]
            line_gap = 6 * mm
            for label, value in payment_rows:
                c.drawString(label_x2, pay_y, label)
                c.drawString(colon_x, pay_y, ":")
                c.drawString(value_x2, pay_y, value)
                pay_y -= line_gap

        with zipfile.ZipFile(zip_buffer, "w") as zf:
            for merchant in df[merchant_col].dropna().unique():
                m_df = df[df[merchant_col] == merchant].copy()
                m_df = compute_balances(m_df)

                net_due = float(m_df["_accumulated"].dropna().iloc[-1]) if len(m_df) and m_df["_accumulated"].notna().any() else 0.0

                pdf_buffer = io.BytesIO()
                c = canvas.Canvas(pdf_buffer, pagesize=A4)
                width, height = A4

                # ========= PAGE MARGINS =========
                left = 20 * mm
                right = 20 * mm
                usable_w = width - left - right

                # table placement window
                table_top_y = draw_header(c, merchant, left, width, height)

                # Reserve a bottom area (totals + payment block) on first page only.
                # If table can't fit above it, we paginate.
                bottom_reserved = 105 * mm  # tuned to your totals+payment block
                table_bottom_limit = 20 * mm + bottom_reserved
                table_available_h_first = table_top_y - table_bottom_limit

                # ========== TABLE DATA ==========
                table_header = [
                    "Date",
                    "Document No.",
                    "External Doc No.",   # <-- renamed from Type
                    "Original\nAmount",
                    "Payment\nAmount",
                    "Document\nAmount",
                    "Accumulated\nBalance",
                ]

                table_rows = []
                for _, row in m_df.iterrows():
                    table_rows.append([
                        p(fmt_text(row.get(date_col))),
                        p(fmt_text(row.get(doc_col))),
                        p(fmt_text(row.get(external_doc_col))),  # <-- mapped to external doc column
                        fmt_money(row.get("_original")),
                        fmt_money(row.get("_payment")),
                        fmt_money(row.get("_document_amt")),
                        fmt_money(row.get("_accumulated")),
                    ])

                # widths (slightly adjusted for longer header)
                col_widths = [
                    18 * mm,  # Date
                    36 * mm,  # Document No.
                    40 * mm,  # External Doc No.
                    21 * mm,  # Original Amount
                    21 * mm,  # Payment Amount
                    21 * mm,  # Document Amount
                    24 * mm,  # Accumulated Balance
                ]

                if sum(col_widths) > usable_w:
                    scale = usable_w / sum(col_widths)
                    col_widths = [w * scale for w in col_widths]

                # ---------- Try fit on first page by scaling ----------
                font_size = 8
                pad_top = 2
                pad_bottom = 2

                table_data_full = [table_header] + table_rows

                def table_height_for(font_sz, pt, pb, data):
                    t = make_main_table(data, col_widths, font_size=font_sz, pad_top=pt, pad_bottom=pb)
                    _, h = t.wrap(0, 0)
                    return t, h

                main_table, main_h = table_height_for(font_size, pad_top, pad_bottom, table_data_full)

                # progressively shrink if needed (still single page attempt)
                while main_h > table_available_h_first and font_size > 6:
                    font_size -= 1
                    pad_top = max(1, pad_top - 0.5)
                    pad_bottom = max(1, pad_bottom - 0.5)
                    main_table, main_h = table_height_for(font_size, pad_top, pad_bottom, table_data_full)

                if main_h <= table_available_h_first:
                    # draw table on first page + totals/payment
                    table_x = left
                    table_y = table_top_y - main_h
                    main_table.drawOn(c, table_x, table_y)

                    # totals/payment block below table
                    draw_totals_and_payment(
                        c,
                        left=left,
                        table_x=table_x,
                        col_widths=col_widths,
                        total_y_start=table_y,
                        net_due=net_due,
                    )
                else:
                    # ---------- Paginate: split rows across pages ----------
                    # We keep header on every page.
                    # Page 1 has less room (because totals/payment at bottom).
                    # Subsequent pages can use almost full height.
                    def page_limits(first_page: bool):
                        if first_page:
                            top = table_top_y
                            bottom = table_bottom_limit
                        else:
                            top = height - 25 * mm
                            bottom = 20 * mm
                        return top, bottom, top - bottom

                    # Use a stable readable size for multi-page
                    font_size = 8
                    pad_top = 2
                    pad_bottom = 2

                    remaining = table_rows[:]
                    first = True
                    table_x = left

                    while remaining:
                        if first:
                            top, bottom, avail_h = page_limits(True)
                        else:
                            c.showPage()
                            draw_header(c, merchant, left, width, height)
                            top, bottom, avail_h = page_limits(False)

                        # Build up rows until it would overflow
                        page_data = [table_header]
                        idx = 0
                        best_table = None
                        best_h = None

                        while idx < len(remaining):
                            candidate = page_data + [remaining[idx]]
                            t, h = table_height_for(font_size, pad_top, pad_bottom, candidate)
                            if h <= avail_h:
                                page_data = candidate
                                best_table = t
                                best_h = h
                                idx += 1
                            else:
                                break

                        # Safety: if even 1 row doesn't fit, force it (shouldn't happen in normal cases)
                        if best_table is None:
                            best_table, best_h = table_height_for(font_size, pad_top, pad_bottom, [table_header] + [remaining[0]])
                            idx = 1

                        table_y = top - best_h
                        best_table.drawOn(c, table_x, table_y)

                        # consume
                        remaining = remaining[idx:]
                        first = False

                    # After finishing table pages, put totals/payment on a final page
                    c.showPage()
                    draw_header(c, merchant, left, width, height)
                    # Put totals/payment near mid-lower area
                    draw_totals_and_payment(
                        c,
                        left=left,
                        table_x=left,
                        col_widths=col_widths,
                        total_y_start=height - 55 * mm,
                        net_due=net_due,
                    )

                c.save()
                pdf_buffer.seek(0)

                safe_name = str(merchant).replace("/", "_").replace("\\", "_")
                zf.writestr(f"SOA_{safe_name}.pdf", pdf_buffer.read())

        zip_buffer.seek(0)
        st.success("ZIP Ready")
        st.download_button(
            "Download ZIP",
            data=zip_buffer,
            file_name="SOA_PDFs.zip",
            mime="application/zip",
        )
