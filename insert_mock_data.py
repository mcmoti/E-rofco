import time
from app import app, db
from models import Application, Farmer

def insert_mock_data():
    with app.app_context():
        # Insert some mock applications
        mock_apps = [
            {
                "id": "APP-2026-0001",
                "member_name": "Gabriel Omondi",
                "member_id": "12345678",
                "zone": "Kibos Sector",
                "acreage": 5.5,
                "requested_amount": 50000.0,
                "purpose": "Fertilizer & Inputs Advance",
                "estimated_tonnage": 192.5,
                "gross_valuation": 1058750.0,
                "status": "Pending Field Assessment",
                "guarantor_name": "Jane Doe",
                "guarantor_id": "87654321",
                "loan_type": "Long-Term",
                "committee_notes": "Requested Term: 6 Months",
                "branch_id": 1
            },
            {
                "id": "APP-2026-0002",
                "member_name": "Mary Wanjiku",
                "member_id": "23456789",
                "zone": "Chemelil Sector",
                "acreage": 3.0,
                "requested_amount": 30000.0,
                "purpose": "Harvest Labor Costs",
                "estimated_tonnage": 105.0,
                "gross_valuation": 577500.0,
                "status": "Pending Field Assessment",
                "guarantor_name": "John Smith",
                "guarantor_id": "98765432",
                "loan_type": "Long-Term",
                "committee_notes": "Requested Term: 3 Months",
                "branch_id": 1
            },
            {
                "id": "APP-2026-0003",
                "member_name": "Peter Njoroge",
                "member_id": "34567890",
                "zone": "West Valley Sector",
                "acreage": 8.0,
                "requested_amount": 80000.0,
                "purpose": "Mechanized Tractor Tillage",
                "estimated_tonnage": 280.0,
                "gross_valuation": 1540000.0,
                "status": "Pending Field Assessment",
                "guarantor_name": "Alice Johnson",
                "guarantor_id": "09876543",
                "loan_type": "Long-Term",
                "committee_notes": "Requested Term: 12 Months",
                "branch_id": 1
            },
            {
                "id": "APP-2026-0004",
                "member_name": "Sarah Ochieng",
                "member_id": "45678901",
                "zone": "Kibos Sector",
                "acreage": 4.5,
                "requested_amount": 45000.0,
                "purpose": "Fertilizer & Inputs Advance",
                "estimated_tonnage": 157.5,
                "gross_valuation": 866250.0,
                "status": "Approved",
                "approved_amount": 45000.0,
                "guarantor_name": "David Brown",
                "guarantor_id": "10987654",
                "loan_type": "Long-Term",
                "committee_notes": "Approved for full amount. Good crop health.",
                "branch_id": 1,
                "net_valuation": 736312.5,
                "max_cap": 368156.25,
                "crop_health": "Grade A",
                "cane_stage": "Ready for Harvest"
            },
            {
                "id": "APP-2026-0005",
                "member_name": "Michael Kiprotich",
                "member_id": "56789012",
                "zone": "Chemelil Sector",
                "acreage": 6.0,
                "requested_amount": 60000.0,
                "purpose": "Emergency Cash Micro-Advance",
                "estimated_tonnage": 210.0,
                "gross_valuation": 1155000.0,
                "status": "Approved (Override)",
                "approved_amount": 60000.0,
                "guarantor_name": "Emma Davis",
                "guarantor_id": "21098765",
                "loan_type": "Long-Term",
                "committee_notes": "Approved override due to long standing relationship.",
                "branch_id": 1,
                "net_valuation": 981750.0,
                "max_cap": 490875.0,
                "crop_health": "Grade B",
                "cane_stage": "Maturation"
            },
            {
                "id": "APP-2026-0006",
                "member_name": "Lucy Kamau",
                "member_id": "67890123",
                "zone": "West Valley Sector",
                "acreage": 2.5,
                "requested_amount": 25000.0,
                "purpose": "Harvest Labor Costs",
                "estimated_tonnage": 87.5,
                "gross_valuation": 481250.0,
                "status": "Rejected",
                "approved_amount": 0.0,
                "guarantor_name": "James Wilson",
                "guarantor_id": "32109876",
                "loan_type": "Long-Term",
                "committee_notes": "Rejected due to over-leveraged position and poor crop health.",
                "branch_id": 1,
                "net_valuation": 409062.5,
                "max_cap": 204531.25,
                "crop_health": "Grade C",
                "cane_stage": "Planting"
            },
            {
                "id": "APP-2026-0007",
                "member_name": "Daniel Mutuku",
                "member_id": "78901234",
                "zone": "Kibos Sector",
                "acreage": 7.0,
                "requested_amount": 70000.0,
                "purpose": "Mechanized Tractor Tillage",
                "estimated_tonnage": 245.0,
                "gross_valuation": 1347500.0,
                "status": "Pending Committee Review",
                "guarantor_name": "Sophia Moore",
                "guarantor_id": "43210987",
                "loan_type": "Long-Term",
                "committee_notes": "Requested Term: 12 Months\n[Assessor Location]: Visited Farm\n[Assessor Notes]: Looks healthy",
                "branch_id": 1,
                "net_valuation": 1145375.0,
                "max_cap": 572687.5,
                "crop_health": "Grade A",
                "cane_stage": "Maturation"
            }
        ]
        
        for app_data in mock_apps:
            # Check if exists
            existing = Application.query.filter_by(id=app_data["id"]).first()
            if not existing:
                app_record = Application(**app_data)
                db.session.add(app_record)
        
        # Add a couple of mock farmers
        farmers = [
            {"name": "Gabriel Omondi", "phone": "0712345678", "id_no": "12345678", "location": "Kibos Sector"},
            {"name": "Mary Wanjiku", "phone": "0723456789", "id_no": "23456789", "location": "Chemelil Sector"}
        ]
        
        for f in farmers:
            existing = Farmer.query.filter_by(phone=f["phone"]).first()
            if not existing:
                farmer = Farmer(**f)
                db.session.add(farmer)
                
        db.session.commit()
        print("Mock data inserted successfully!")

if __name__ == "__main__":
    insert_mock_data()
