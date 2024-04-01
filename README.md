# robot-server

The goal of this task is to create a TCP server to help direct robots over the internet.

The server is supposed to direct robots to the center of the coordinate grid, avoiding any obstacles. Since the server doesnt know the location of obstacles beforehand, the obstacles are detected by the response of the robot: if the coordinates of the robot are unchanged, then it encountered an obstacle. It is guaranteed that every obstacle will have a path around it, and there are no obstacles near the center.

Once at the center, the robot is supposed to send the encoded message to the server in packets. The server is supposed to receive these packets, and direct the robot to continue sending them.
