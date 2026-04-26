"""
Customer Persona Report API endpoints.
"""

import logging
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from services.data_models.schemas import PersonaReportRequest, PersonaReportResponse
from config import get_settings
from services.persona_service import PersonaService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/personas")
settings = get_settings()

# Initialize persona service
persona_service = PersonaService()


@router.post("/reports/generate", response_model=PersonaReportResponse)
async def generate_persona_report(req: PersonaReportRequest):
    """
    Generate a personalized customer persona report.

    Args:
        req: Report generation request with customer data

    Returns:
        PersonaReportResponse with generated report or error

    Example:
        POST /api/v1/personas/reports/generate
        {
            "customer_id": "cust_123",
            "include_sentiment": true,
            "include_recommendations": true
        }
    """
    try:
        logger.info(
            f"Generating persona report for customer: {req.customer_id}")

        # Generate report
        report = await persona_service.generate_report(req)

        return PersonaReportResponse(
            success=True,
            report=report,
            report_id=report.id,
            message="Report generated successfully"
        )

    except Exception as e:
        logger.error(
            f"Error generating persona report: {str(e)}", exc_info=True)
        return PersonaReportResponse(
            success=False,
            error=str(e),
            message="Failed to generate report"
        )


@router.get("/reports/{report_id}", response_model=PersonaReportResponse)
async def get_persona_report(report_id: str):
    """
    Retrieve a cached persona report by ID.

    Args:
        report_id: Unique report identifier

    Returns:
        PersonaReportResponse with report data
    """
    try:
        logger.info(f"Retrieving persona report: {report_id}")

        report = persona_service.get_report(report_id)

        if not report:
            raise HTTPException(status_code=404, detail="Report not found")

        return PersonaReportResponse(
            success=True,
            report=report,
            report_id=report_id,
            message="Report retrieved successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving persona report: {str(e)}")
        return PersonaReportResponse(
            success=False,
            error=str(e),
            message="Failed to retrieve report"
        )


@router.get("/reports/sample", response_model=PersonaReportResponse)
async def get_sample_persona_report():
    """
    Get a sample persona report for demonstration.

    Returns:
        PersonaReportResponse with sample Budget Traveler persona
    """
    try:
        logger.info("Generating sample persona report")

        sample_report = persona_service.load_sample_report()

        return PersonaReportResponse(
            success=True,
            report=sample_report,
            report_id="sample_001",
            message="Sample report generated successfully"
        )

    except Exception as e:
        logger.error(f"Error generating sample report: {str(e)}")
        return PersonaReportResponse(
            success=False,
            error=str(e),
            message="Failed to generate sample report"
        )


@router.get("/")
async def list_personas(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    List all available personas.

    Args:
        limit: Maximum personas to return
        offset: Pagination offset

    Returns:
        List of personas with metadata
    """
    try:
        personas = persona_service.list_personas(limit=limit, offset=offset)
        return {
            "personas": personas,
            "total": len(personas),
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        logger.error(f"Error listing personas: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{persona_id}")
async def get_persona(persona_id: str):
    """
    Get a specific persona by ID.

    Args:
        persona_id: Persona identifier

    Returns:
        Persona data and traits
    """
    try:
        persona = persona_service.load_persona(persona_id)
        if not persona:
            raise HTTPException(status_code=404, detail="Persona not found")
        return persona
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving persona: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
