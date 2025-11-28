from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, OperationalError
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging
import json
import traceback
from datetime import datetime
import uuid

# Custom exception hierarchy
class NMSError(Exception):
    """Base exception for NMS application errors."""

    def __init__(self, message: str, error_code: str = "INTERNAL_ERROR",
                 status_code: int = 500, details: Optional[Dict[str, Any]] = None,
                 user_message: Optional[str] = None, troubleshooting: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        self.user_message = user_message or message
        self.troubleshooting = troubleshooting
        self.error_id = str(uuid.uuid4())[:8]

class ValidationError(NMSError):
    """Validation and input errors."""
    def __init__(self, message: str, field: Optional[str] = None, **kwargs):
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            status_code=400,
            user_message=f"Invalid input: {message}",
            troubleshooting="Please check your input and try again. Contact support if the problem persists.",
            **kwargs
        )
        if field:
            self.details['field'] = field

class ResourceNotFoundError(NMSError):
    """Resource not found errors."""
    def __init__(self, resource_type: str, resource_id: Any, **kwargs):
        super().__init__(
            message=f"{resource_type} with ID '{resource_id}' not found",
            error_code="RESOURCE_NOT_FOUND",
            status_code=404,
            user_message=f"The {resource_type.lower()} you're looking for doesn't exist.",
            troubleshooting=f"Verify the {resource_type.lower()} ID is correct and try again.",
            **kwargs
        )
        self.details.update({
            'resource_type': resource_type,
            'resource_id': resource_id
        })

class DatabaseError(NMSError):
    """Database-related errors."""
    def __init__(self, message: str, operation: str, **kwargs):
        super().__init__(
            message=message,
            error_code="DATABASE_ERROR",
            status_code=500,
            user_message="A database error occurred. Please try again.",
            troubleshooting="If this persists, the database may be temporarily unavailable. Contact support.",
            **kwargs
        )
        self.details['operation'] = operation

class NetworkError(NMSError):
    """Network and connectivity errors."""
    def __init__(self, message: str, target: str, **kwargs):
        super().__init__(
            message=message,
            error_code="NETWORK_ERROR",
            status_code=503,
            user_message=f"Unable to connect to {target}. Please check your network connection.",
            troubleshooting="Verify network connectivity and target availability. Try again in a few moments.",
            **kwargs
        )
        self.details['target'] = target

class DiscoveryError(NMSError):
    """Network discovery specific errors."""
    def __init__(self, message: str, discovery_run_id: Optional[int] = None, **kwargs):
        super().__init__(
            message=message,
            error_code="DISCOVERY_ERROR",
            status_code=500,
            user_message="Network discovery failed. Please check the discovery logs for details.",
            troubleshooting="Review discovery configuration and network access. Check logs for specific error details.",
            **kwargs
        )
        if discovery_run_id:
            self.details['discovery_run_id'] = discovery_run_id

class AuthenticationError(NMSError):
    """Authentication and authorization errors."""
    def __init__(self, message: str = "Authentication required", **kwargs):
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_ERROR",
            status_code=401,
            user_message="Authentication required to access this resource.",
            troubleshooting="Please log in and try again.",
            **kwargs
        )

class PermissionError(NMSError):
    """Permission and authorization errors."""
    def __init__(self, message: str = "Insufficient permissions", **kwargs):
        super().__init__(
            message=message,
            error_code="PERMISSION_ERROR",
            status_code=403,
            user_message="You don't have permission to perform this action.",
            troubleshooting="Contact your administrator to request the necessary permissions.",
            **kwargs
        )

# Error response models
class ErrorDetail(BaseModel):
    error_id: str
    error_code: str
    message: str
    user_message: str
    troubleshooting: Optional[str] = None
    timestamp: str
    path: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail

# Logging configuration
class NMSLogger:
    def __init__(self, name: str = "nms"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)

        # Remove existing handlers
        self.logger.handlers = []

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

        # File handler for errors
        error_handler = logging.FileHandler('logs/nms_errors.log')
        error_handler.setLevel(logging.WARNING)
        error_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - ERROR_ID:%(error_id)s - %(message)s'
        )
        error_handler.setFormatter(error_formatter)
        self.logger.addHandler(error_handler)

        # File handler for all logs
        all_handler = logging.FileHandler('logs/nms.log')
        all_handler.setLevel(logging.DEBUG)
        all_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        all_handler.setFormatter(all_formatter)
        self.logger.addHandler(all_handler)

    def log_error(self, error: NMSError, request: Optional[Request] = None, exc_info=None):
        """Log an NMS error with full context."""
        extra = {
            'error_id': error.error_id,
            'error_code': error.error_code,
            'status_code': error.status_code,
            'user_message': error.user_message,
            'details': json.dumps(error.details) if error.details else None,
            'path': str(request.url) if request else None,
            'method': request.method if request else None,
            'user_agent': request.headers.get('user-agent') if request else None,
            'client_ip': self._get_client_ip(request) if request else None
        }

        self.logger.error(
            f"Error {error.error_code}: {error.message}",
            extra=extra,
            exc_info=exc_info
        )

    def log_request(self, request: Request, response: Optional[Response] = None,
                   duration: Optional[float] = None):
        """Log API request details."""
        extra = {
            'method': request.method,
            'path': str(request.url),
            'status_code': response.status_code if response else None,
            'duration': f"{duration:.2f}s" if duration else None,
            'client_ip': self._get_client_ip(request),
            'user_agent': request.headers.get('user-agent')
        }

        if response and response.status_code >= 400:
            self.logger.warning(f"Request failed: {request.method} {request.url}", extra=extra)
        else:
            self.logger.info(f"Request: {request.method} {request.url}", extra=extra)

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request."""
        x_forwarded_for = request.headers.get('x-forwarded-for')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.client.host if request.client else "unknown"

# Global logger instance
logger = NMSLogger()

# Error handling middleware
async def error_handling_middleware(request: Request, call_next):
    """Global error handling middleware."""
    start_time = datetime.utcnow()

    try:
        response = await call_next(request)
        duration = (datetime.utcnow() - start_time).total_seconds()

        # Log successful requests
        logger.log_request(request, response, duration)

        return response

    except NMSError as e:
        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.log_error(e, request, exc_info=True)

        error_detail = ErrorDetail(
            error_id=e.error_id,
            error_code=e.error_code,
            message=e.message,
            user_message=e.user_message,
            troubleshooting=e.troubleshooting,
            timestamp=datetime.utcnow().isoformat(),
            path=str(request.url),
            details=e.details
        )

        return JSONResponse(
            status_code=e.status_code,
            content=ErrorResponse(error=error_detail).dict()
        )

    except HTTPException as e:
        duration = (datetime.utcnow() - start_time).total_seconds()

        # Convert HTTPException to NMS error
        nms_error = NMSError(
            message=str(e.detail),
            error_code="HTTP_EXCEPTION",
            status_code=e.status_code,
            user_message=str(e.detail),
            troubleshooting="Check the request parameters and try again."
        )

        logger.log_error(nms_error, request)

        error_detail = ErrorDetail(
            error_id=nms_error.error_id,
            error_code=nms_error.error_code,
            message=nms_error.message,
            user_message=nms_error.user_message,
            troubleshooting=nms_error.troubleshooting,
            timestamp=datetime.utcnow().isoformat(),
            path=str(request.url)
        )

        return JSONResponse(
            status_code=e.status_code,
            content=ErrorResponse(error=error_detail).dict()
        )

    except SQLAlchemyError as e:
        duration = (datetime.utcnow() - start_time).total_seconds()

        # Determine specific database error type
        if isinstance(e, IntegrityError):
            nms_error = DatabaseError(
                message=str(e),
                operation="integrity_check",
                user_message="Data integrity violation. Please check your input.",
                troubleshooting="Ensure data doesn't conflict with existing records."
            )
        elif isinstance(e, OperationalError):
            nms_error = DatabaseError(
                message=str(e),
                operation="database_operation",
                user_message="Database temporarily unavailable.",
                troubleshooting="Try again in a few moments. Contact support if persistent."
            )
        else:
            nms_error = DatabaseError(
                message=str(e),
                operation="database_query",
                user_message="Database error occurred.",
                troubleshooting="Contact support with the error ID."
            )

        logger.log_error(nms_error, request, exc_info=True)

        error_detail = ErrorDetail(
            error_id=nms_error.error_id,
            error_code=nms_error.error_code,
            message=nms_error.message,
            user_message=nms_error.user_message,
            troubleshooting=nms_error.troubleshooting,
            timestamp=datetime.utcnow().isoformat(),
            path=str(request.url),
            details={"sql_error_type": type(e).__name__}
        )

        return JSONResponse(
            status_code=nms_error.status_code,
            content=ErrorResponse(error=error_detail).dict()
        )

    except Exception as e:
        duration = (datetime.utcnow() - start_time).total_seconds()

        # Generic error handling
        nms_error = NMSError(
            message=str(e),
            error_code="UNEXPECTED_ERROR",
            status_code=500,
            user_message="An unexpected error occurred.",
            troubleshooting="Contact support with the error ID for assistance."
        )

        logger.log_error(nms_error, request, exc_info=True)

        error_detail = ErrorDetail(
            error_id=nms_error.error_id,
            error_code=nms_error.error_code,
            message=nms_error.message,
            user_message=nms_error.user_message,
            troubleshooting=nms_error.troubleshooting,
            timestamp=datetime.utcnow().isoformat(),
            path=str(request.url),
            details={"traceback": traceback.format_exc()}
        )

        return JSONResponse(
            status_code=500,
            content=ErrorResponse(error=error_detail).dict()
        )

# Utility functions for error handling
def handle_database_operation(operation_name: str, operation_func):
    """Wrapper for database operations with error handling."""
    try:
        return operation_func()
    except IntegrityError as e:
        raise DatabaseError(
            message=f"Integrity error in {operation_name}: {str(e)}",
            operation=operation_name,
            details={"constraint_violation": True}
        )
    except OperationalError as e:
        raise DatabaseError(
            message=f"Database operation failed in {operation_name}: {str(e)}",
            operation=operation_name,
            details={"connection_issue": True}
        )
    except SQLAlchemyError as e:
        raise DatabaseError(
            message=f"Database error in {operation_name}: {str(e)}",
            operation=operation_name
        )

def validate_discovery_request(root_ip: str, community: str = None):
    """Validate discovery request parameters."""
    from ipaddress import IPv4Address, IPv4Network

    try:
        # Validate IP address
        IPv4Address(root_ip)
    except ValueError:
        raise ValidationError(
            message=f"Invalid IP address format: {root_ip}",
            field="root_ip"
        )

    # Check if it's a network range (contains /)
    if '/' in root_ip:
        try:
            network = IPv4Network(root_ip, strict=False)
            if network.prefixlen < 24:
                raise ValidationError(
                    message=f"Network prefix too broad: {network.prefixlen} bits. Maximum allowed is /24.",
                    field="root_ip",
                    details={"prefix_length": network.prefixlen}
                )
        except ValueError as e:
            raise ValidationError(
                message=f"Invalid network format: {str(e)}",
                field="root_ip"
            )

    if community and len(community) > 50:
        raise ValidationError(
            message="SNMP community string too long",
            field="snmp_community"
        )

def create_success_response(data: Any, message: str = "Success") -> Dict[str, Any]:
    """Create standardized success response."""
    return {
        "success": True,
        "message": message,
        "data": data,
        "timestamp": datetime.utcnow().isoformat()
    }

def create_paginated_response(
    data: list,
    total: int,
    page: int,
    per_page: int,
    message: str = "Data retrieved successfully"
) -> Dict[str, Any]:
    """Create standardized paginated response."""
    return {
        "success": True,
        "message": message,
        "data": data,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": (total + per_page - 1) // per_page
        },
        "timestamp": datetime.utcnow().isoformat()
    }
