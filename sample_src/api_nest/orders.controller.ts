// Nest controller for orders.
// Nest splits a route across two decorators: @Controller gives the prefix, the
// method decorator gives the verb and the suffix. Its class decorators are also
// real evidence of a layer, where a plain JS class offers only its name.
import { Controller, Get, Post } from "@nestjs/common";

@Controller("nest/orders")
export class OrdersController {
  // Place a new order.
  @Post()
  create(body: object) {
    return { created: true, ...body };
  }

  // Fetch one order by id.
  @Get(":id")
  findOne(id: string) {
    return { id, status: "open" };
  }
}
