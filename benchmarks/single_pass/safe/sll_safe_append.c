struct Node {
    int value;
    struct Node *next;
};

void sll_safe_append(struct Node *root, int value) {
    struct Node *last;
    struct Node *last_next;
    struct Node *first;

    first = root; //0

    if(!first) {
        first = malloc(sizeof(struct Node));
        first -> value = value;
    }
    else {
        last = first;
        last_next = last->next; //5
        while(last_next) {
            last = last_next;
            last_next = last->next; //8
        }
        last_next = malloc(sizeof(struct Node)); //9
        last_next->value = value;
        last->next = last_next;
    }
}
