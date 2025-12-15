struct Node {
    int value;
    struct Node *next;
};    

void sll_unsafe_find(struct Node **head, int key) {
    struct Node *tmp;
    struct Node *x;
    struct Node *result_node;
    int result;

    x = *head;

    while(x != 0) {
        result = x->value;
        if(result == key) {
            result_node = x;
            x = 0;
        }
        else {
            x = x->next;
        }
    }

    result = x->value;
}