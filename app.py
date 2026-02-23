import io
import zipfile
from datetime import date
import pandas as pd
import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

st.title("SOA Mass Generator - Australia")

statement_as_at = st.date_input("Statement as at", value=date(2026,1,31))
subsidiary = "ShopBack Australia Pty Ltd"

uploaded = st.file_uploader("Upload CSV", type=["csv"])

if uploaded:

    df = pd.read_csv(uploaded)
    st.write("Preview:")
    st.dataframe(df.head())

    merchant_col = st.selectbox("Merchant Column", df.columns)

    date_col = st.selectbox("Date Column", df.columns)
    doc_col = st.selectbox("Doc Number Column", df.columns)
    type_col = st.selectbox("Type Column", df.columns)
    original_col = st.selectbox("Original Amount Column", df.columns)
    payment_col = st.selectbox("Payment Amount Column", df.columns)
    document_col = st.selectbox("Document Column", df.columns)
    acc_col = st.selectbox("Accumulated Balance Column", df.columns)

    if st.button("Generate ZIP"):

        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "w") as zf:

            for merchant in df[merchant_col].dropna().unique():

                m_df = df[df[merchant_col] == merchant]

                pdf_buffer = io.BytesIO()
                c = canvas.Canvas(pdf_buffer, pagesize=A4)
                width, height = A4

                y = height - 30*mm

                c.setFont("Helvetica-Bold", 16)
                c.drawCentredString(width/2, y, "STATEMENT OF ACCOUNT")
                y -= 20

                c.setFont("Helvetica", 11)
                c.drawString(20*mm, y, "To:")
                y -= 15
                c.drawString(20*mm, y, str(merchant))

                c.drawRightString(width-20*mm, height-40,
                                  f"Statement as at {statement_as_at.strftime('%d-%b-%Y')}")
                c.drawRightString(width-20*mm, height-55,
                                  f"Subsidiary {subsidiary}")

                y -= 30

                c.setFont("Helvetica-Bold", 10)
                headers = ["Date","Doc Number","Type",
                           "Original","Payment","Document","Accumulated"]
                x_positions = [20, 80, 150, 240, 310, 380, 450]

                for i,h in enumerate(headers):
                    c.drawString(x_positions[i], y, h)

                y -= 15
                c.setFont("Helvetica", 9)

                for _,row in m_df.iterrows():

                    values = [
                        row.get(date_col,""),
                        row.get(doc_col,""),
                        row.get(type_col,""),
                        row.get(original_col,""),
                        row.get(payment_col,""),
                        row.get(document_col,""),
                        row.get(acc_col,"")
                    ]

                    for i,v in enumerate(values):
                        text = "" if pd.isna(v) else str(v)
                        c.drawString(x_positions[i], y, text)

                    y -= 15
                    if y < 80:
                        c.showPage()
                        y = height - 40

                acc_num = pd.to_numeric(m_df[acc_col], errors="coerce")
                if acc_num.notna().any():
                    net_due = acc_num.dropna().iloc[-1]
                else:
                    net_due = 0

                y -= 20
                c.setFont("Helvetica-Bold", 11)
                c.drawString(20*mm, y, "NET AMOUNT DUE FROM YOU (AUD)")
                c.drawRightString(width-20*mm, y, f"{net_due:,.2f}")

                y -= 30
                c.setFont("Helvetica", 10)
                c.drawString(20*mm, y, "Payment should be made to the following details:")
                y -= 15

                payment_details = [
                    "Bank Name : ANZ Banking Group Limited",
                    "Account Name : ShopBack Australia Pty Ltd",
                    "Account Number : 012010 307004743",
                    "SWIFT Code : ANZBAU3M",
                    "Branch Code :",
                    "Currency : AUD"
                ]

                for line in payment_details:
                    c.drawString(20*mm, y, line)
                    y -= 15

                c.save()
                pdf_buffer.seek(0)

                filename = f"SOA_{merchant}.pdf"
                zf.writestr(filename, pdf_buffer.read())

        zip_buffer.seek(0)

        st.success("ZIP Ready")
        st.download_button("Download ZIP",
                           data=zip_buffer,
                           file_name="SOA_PDFs.zip",
                           mime="application/zip")
