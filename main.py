import socket
import threading

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
socket_num = 6666

# Try all available sockets above 6666
while True:
    try:
        s.bind(("localhost", socket_num))
        print(f"Started server on port {socket_num}")
        break
    except:
        socket_num += 1


# Custom exception class to ease returning from functions
class Error(Exception):
    def __init__(self, message):
        self.message = message


class Robot:

    # Constructor of class, initialize variables
    def __init__(self, c):
        self.queue = []  # Queue of robot responses
        self.c = c  # Connection socket
        self.response = ""  # Current response
        self.remainder = ""  # Remainder after delimiter of robot response
        self.coords = [0, 0]
        self.heading = 0  # Robot direction as compass heading
        self.collisions = 0
        self.keys = [[23019, 32037], [32037, 29295], [18789, 13603], [16443, 29533], [18189, 21952]]

    # Uses queue of responses to get next robot response
    # Expected length optimizes the algorithm such that if a message is longer than the
    # expected length, a syntax error is sent before the delimiter is received.
    # Expected length can be set to -1 if the expected length is not known beforehand.
    def get_response(self, expected_length):
        # Check if there are queued responses
        if len(self.queue) == 0:
            # Take remainder from last robot response
            string = self.remainder
            string += self.c.recv(512).decode()  # Get message string 512 bytes

            while "\a\b" not in string:  # While complete message was not received
                # Check if without remainder message reaches maximum expected length
                if expected_length != -1 and len(string) >= expected_length:
                    raise Error("301 SYNTAX ERROR\a\b")

                # Listen for continuation of message
                string += self.c.recv(512).decode()

            self.queue = string.split("\a\b")  # Split message by delimiter
            self.remainder = self.queue[-1]  # The last part is the remainder
            del self.queue[-1]  # Delete last element of queue because of the way split() works

            # Save the next element in queue as the new response
            new_response = self.queue[0]
            # Remove from queue
            del self.queue[0]

        else:
            # Queue is not empty, so just remove from it.
            new_response = self.queue[0]
            del self.queue[0]

        # If the new robot response is "FULL POWER" then it can only be received if the
        # previous response was "RECHARGING"
        if self.response == "RECHARGING" and new_response != "FULL POWER":
            raise Error("302 LOGIC ERROR\a\b")

        elif new_response == "RECHARGING":
            self.response = new_response
            self.c.settimeout(5)  # Extend socket timeout to allow recharging
            self.get_response(12)  # Await FULL POWER message
            self.c.settimeout(1)  # Reset timeout to normal communication
            self.get_response(expected_length)  # Await actual next response

        else:
            # Normal robot response, continue as usual
            self.response = new_response

    # Updates the robot's coordinate pair. Uses get_response()
    def get_coords(self):
        self.get_response(12)

        # Split string by spaces
        result = self.response.split(" ")

        # Check string is in format 'OK x y' and x y are digits
        if len(result) != 3 or result[0] != "OK":
            raise Error("301 SYNTAX ERROR\a\b")

        # Try converting result to integer and save to coordinates
        try:
            self.coords = [int(result[1]), int(result[2])]
        except:
            raise Error("301 SYNTAX ERROR\a\b")

    # Authentication process
    def authenticate(self):
        # Try getting robot username
        self.get_response(20)
        username = self.response

        # Validate length of username
        if len(username) > 18:
            raise Error("301 SYNTAX ERROR\a\b")

        # Request authentication key
        self.c.send("107 KEY REQUEST\a\b".encode())

        # Try getting auth key
        self.get_response(5)
        key = self.response

        # Validate length of auth key or if it is a digit
        if len(key) > 3 or not key.isdigit():
            raise Error("301 SYNTAX ERROR\a\b")

        # Key is valid, convert it to integer
        key = int(key)

        # Validate if auth key is in correct range
        if key < 0 or key > 4:
            raise Error("303 KEY OUT OF RANGE\a\b")

        # Calculate username hash
        username_hash = 0
        for i in username:
            username_hash += ord(i)
        username_hash *= 1000
        username_hash %= 65536

        # Calculate server-side hash and send it to client
        server_hash = username_hash + self.keys[key][0]
        server_hash %= 65536
        self.c.send(f"{server_hash}\a\b".encode())

        # Try getting client confirmation
        self.get_response(7)
        client_confirmation = self.response

        # If confirmation is too big or is not a number, it is invalid
        if len(client_confirmation) > 5 or not client_confirmation.isdigit():
            raise Error("301 SYNTAX ERROR\a\b")

        client_confirmation = int(client_confirmation)

        # Compute expected client hash
        client_hash = username_hash + self.keys[key][1]
        client_hash %= 65536

        # Compare client confirmation and expected client hash
        if client_confirmation != client_hash:
            raise Error("300 LOGIN FAILED\a\b")

        # Authorization completed, send confirmation
        self.c.send("200 OK\a\b".encode())

    # Gets the robot's starting position and direction
    def get_initial_conditions(self):
        # Instruct robot to turn to get initial coordinates
        self.c.send("103 TURN LEFT\a\b".encode())
        self.get_coords()

        # Save current coordinates to calculate difference
        old_x = self.coords[0]
        old_y = self.coords[1]

        # Instruct robot to move to get direction
        self.c.send("102 MOVE\a\b".encode())
        self.get_coords()

        # Direction is the same as the robot's heading
        if self.coords[1] == old_y:
            if self.coords[0] > old_x:
                self.heading = 90

            elif self.coords[0] < old_x:
                self.heading = 270

            # There is an obstacle right in front of the robot.
            else:
                self.collisions += 1
                # Run the function again. It will rotate the robot again
                # and the robot will naturally avoid the obstacle
                self.get_initial_conditions()
        else:
            if self.coords[1] > old_y:
                self.heading = 0
            else:
                self.heading = 180

    # Rotates the robot clockwise until it is facing the correct heading
    def rotate(self, final_heading):
        while self.heading != final_heading:
            self.c.send("104 TURN RIGHT\a\b".encode())
            self.get_coords()
            self.heading = (self.heading + 90) % 360

    # Goes around an obstacle it meets
    # axis parameter is used in determining if the robot reaches target while avoiding obstacle
    def avoid_obstacle(self, axis):
        self.c.send("103 TURN LEFT\a\b".encode())
        self.get_coords()

        self.c.send("102 MOVE\a\b".encode())
        self.get_coords()

        self.c.send("104 TURN RIGHT\a\b".encode())
        self.get_coords()

        self.c.send("102 MOVE\a\b".encode())
        self.get_coords()
        # As the robot is going around the obstacle, it can reach its target axis.
        if self.coords[axis] == 0:
            return

        self.c.send("102 MOVE\a\b".encode())
        self.get_coords()

        self.c.send("104 TURN RIGHT\a\b".encode())
        self.get_coords()

        self.c.send("102 MOVE\a\b".encode())
        self.get_coords()

        self.c.send("103 TURN LEFT\a\b".encode())
        self.get_coords()

    # Robot moves until it reaches 0 coordinate in given axis.
    # Robot goes around every obstacle it encounters using avoid_obstacle() function
    def move(self, axis):
        while self.coords[axis] != 0:
            old = self.coords[axis]

            self.c.send("102 MOVE\a\b".encode())
            self.get_coords()

            if self.coords[axis] == old:
                self.collisions += 1
                if self.collisions > 20:
                    raise Error(None)

                self.avoid_obstacle(axis)

    # Wrapper function for move() and rotate()
    def navigate(self):
        # Determine if robot needs to go left or right to reach 0 coordinate on x-axis
        if self.coords[0] > 0:
            # Need to go to the left
            self.rotate(270)
        elif self.coords[0] < 0:
            # Need to go to the right
            self.rotate(90)

        self.move(0)

        # Determine if robot needs to go up or down to reach 0 coordinate on y-axis
        if self.coords[1] > 0:
            # Need to go down
            self.rotate(180)
        elif self.coords[1] < 0:
            # Need to go up
            self.rotate(0)

        self.move(1)

    def pickup_message(self):
        self.c.send("105 GET MESSAGE\a\b".encode())
        self.get_response(100)
        print(self.response)
        self.c.send("106 LOGOUT\a\b".encode())

    def start(self):
        try:
            # All functions raise appropriate exceptions when encountering errors
            self.c.settimeout(1)
            self.authenticate()
            self.get_initial_conditions()
            self.navigate()
            self.pickup_message()
        except Error as e:
            if e.message is None:
                # No error message to delegate
                pass
            else:
                # Exception class contains an error message which needs to be sent to robot
                self.c.send(e.message.encode())
        except socket.timeout:
            # Robot has timed out, no error message to send
            pass

        self.c.close()


s.listen()
while True:
    conn, addr = s.accept()
    # Create a new Robot class instance for each client
    robot = Robot(conn)
    thread = threading.Thread(target=robot.start, args=())
    thread.start()
