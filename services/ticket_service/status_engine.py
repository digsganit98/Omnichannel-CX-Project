from shared.schemas.tickets import Ticket, TicketStatus


def update_status(ticket: Ticket, status: TicketStatus) -> Ticket:
    ticket.status = status
    return ticket
