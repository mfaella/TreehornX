
struct Node {
    int data;
    struct Node* next;
};

void sll_safe_insert_sorted(struct Node* root, int value) {
    struct Node* newNode;
    struct Node* parent;
    struct Node* current;
    struct Node *next;
    struct Node *null;
    int data;
    int next_data;
    int temp_data;

    // precondition
    current = root;
    while (current) {
        data = current->data;
        next = current->next;
        if (next)  {
            next_data = next->data;
            if (data > next_data) {
                return;
            }
        }
        // current = next;
        current = current->next;
    }

    current = root;

    while (current) {
        temp_data = current->data;
        if (value >= temp_data) { //7
            parent = current; //5
            current = current->next;
        }
        else {
            goto BREAK;
        }
    }
    BREAK:

    newNode = malloc(sizeof(struct Node));
    newNode->data = value;
    newNode->next = current;

    if (parent) {
        parent->next = newNode;
    }
    else {
        root = newNode;
    }

    // postcondition
    current = root;
    while (current) {
        data = current->data;
        next = current->next;
        if (next)  {
            next_data = next->data;
            if (data > next_data) {
                temp_data = null->data;
            }
        }
        current = current->next;
        // current = next;
    }
}
